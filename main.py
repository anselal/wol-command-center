import asyncio
import socket
import json
import os
from quart import Quart, request, jsonify, render_template
from quart_cors import cors
from wakeonlan import send_magic_packet
from icmplib import async_ping
# Feature 1: Import getmac
from getmac import get_mac_address

app = Quart(__name__)
app = cors(app, allow_origin="*")

DATA_FILE = 'machines.json'
machines = []

# --- Helper Functions ---
def load_data():
    global machines
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            machines = json.load(f)
    else:
        machines = []

def save_data():
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        # ensure_ascii=False ensures Greek characters are saved correctly
        json.dump(machines, f, indent=4, ensure_ascii=False)

# Load data on startup
load_data()

# --- Background Task ---
async def check_machine_status():
    while True:
        # Create a copy to iterate safely
        current_machines = machines[:]
        for machine in current_machines:
            try:
                # Privileged=False needs the sysctl tweak mentioned before
                host = await async_ping(machine['ip'], count=1, timeout=0.5, privileged=False)
                machine['status'] = 'online' if host.is_alive else 'offline'
            except Exception as e:
                print(f"Ping Error {machine['ip']}: {e}")
                machine['status'] = 'error'

        await asyncio.sleep(3)

@app.before_serving
async def start_background_tasks():
    app.add_background_task(check_machine_status)

# --- Routes ---

@app.route('/')
async def index():
    return await render_template('dashboard.html')

@app.route('/api/machines', methods=['GET'])
async def get_machines():
    return jsonify(machines)

@app.route('/api/wake', methods=['POST'])
async def wake_machine():
    data = await request.get_json()
    mac = data.get('mac')
    if mac:
        try:
            send_magic_packet(mac)
            return jsonify({"message": f"Packet sent to {mac}"})
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    return jsonify({"error": "No MAC"}), 400

@app.route('/api/add', methods=['POST'])
async def add_machine():
    data = await request.get_json()

    # Generate new ID
    new_id = 1
    if machines:
        new_id = max(m['id'] for m in machines) + 1

    ip = data.get('ip', '').strip()
    mac = data.get('mac', '').strip()
    message = "Machine added successfully."

    # Feature 1: Auto-detect MAC if IP provided but MAC missing
    if ip and not mac:
        try:
            detected_mac = get_mac_address(ip=ip)
            if detected_mac:
                mac = detected_mac
                message = f"Machine added. MAC address auto-detected: {mac}"
            else:
                message = "Machine added. Warning: Could not auto-detect MAC address from IP."
        except Exception as e:
            print(f"MAC Detection Error: {e}")
            message = "Machine added, but MAC detection failed."

    new_machine = {
        "id": new_id,
        "ip": ip,
        "mac": mac,
        "name": data.get('name') or "New Host",
        "user": data.get('user') or "Unknown",
        "status": "offline"
    }
    machines.append(new_machine)
    save_data()

    # Return both data and the status message
    return jsonify({"machine": new_machine, "message": message})

@app.route('/api/delete/<int:machine_id>', methods=['DELETE'])
async def delete_machine(machine_id):
    global machines
    machines = [m for m in machines if m['id'] != machine_id]
    save_data()
    return jsonify({"success": True})

@app.route('/api/update/<int:machine_id>', methods=['PUT'])
async def update_machine(machine_id):
    data = await request.get_json()
    message = "Machine updated successfully."

    for m in machines:
        if m['id'] == machine_id:
            m['ip'] = data.get('ip', m['ip'])

            # Check MAC update logic
            new_mac = data.get('mac')

            # If user explicitly clears MAC (sends empty string) or it's missing,
            # and we have a valid IP, try to re-detect.
            if new_mac is not None:
                clean_mac = new_mac.strip()
                if clean_mac == "" and m['ip']:
                    try:
                        detected_mac = get_mac_address(ip=m['ip'])
                        if detected_mac:
                            m['mac'] = detected_mac
                            message = f"Updated. MAC address auto-detected: {detected_mac}"
                        else:
                            m['mac'] = ""
                            message = "Updated. Warning: Could not resolve MAC address."
                    except:
                        m['mac'] = ""
                else:
                    m['mac'] = clean_mac

            m['user'] = data.get('user', m['user'])
            m['name'] = data.get('name', m['name'])

            save_data()
            return jsonify({"machine": m, "message": message})

    return jsonify({"error": "Not found"}), 404

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)