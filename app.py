from flask import Flask, request, jsonify, render_template
import os
from flask_cors import CORS
import subprocess
from db_config import get_connection
import csv

app = Flask(__name__, template_folder='templates')
CORS(app)

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/system')
def system_page():
    return render_template('system.html')

@app.route('/stations', methods=['GET'])
def get_stations():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT telephone_no, office, station, designation, department, server_ip, sip_username FROM stations")
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(rows)



@app.route('/hotline')
def hotline_page():
    return render_template('hotline.html')

@app.route('/hotline', methods=['POST'])
def configure_hotline():
    data = request.get_json()
    hotline_ext = data.get('hotline_extension')
    target_ext = data.get('target_extension')

    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Insert into MySQL
        sql = "INSERT INTO hotlines (hotline_extension, target_extension) VALUES (%s, %s)"
        cursor.execute(sql, (hotline_ext, target_ext))
        conn.commit()

        # Write to extensions.conf
        with open("/etc/asterisk/extensions.conf", "a") as f:
            f.write(f"\n[hotline-{hotline_ext}]\n")
            f.write(f"exten => s,1,NoOp(Hotline {hotline_ext} to {target_ext})\n")
            f.write(f" same => n,Dial(PJSIP/{target_ext})\n")
            f.write(" same => n,Hangup()\n")

        subprocess.run(["sudo", "asterisk", "-rx", "dialplan reload"])

        return jsonify({"message": "Hotline added successfully"}), 201

    except Exception as e:
        return jsonify({"message": f"Error: {str(e)}"}), 500



@app.route('/stations', methods=['POST'])
def add_station():
    data = request.get_json()
    print("Received data:", data)

    conn = get_connection()
    cursor = conn.cursor()
    sql = """
        INSERT INTO stations (telephone_no, office, station, designation, department, server_ip, sip_username, sip_password)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """
    values = (
        data['telephone'],
        data['office'],
        data['station'],
        data['designation'],
        data['department'],
        
        data['server_ip'],
        data['sip_username'],
        data['sip_password']
    )

    cursor.execute(sql, values)
    conn.commit()
    cursor.close()
    conn.close()

    # SIP Config for pjsip.conf
    sip_config = f"""
[{data['sip_username']}]
type=endpoint
context=default
disallow=all
allow=ulaw
auth=auth{data['sip_username']}
aors={data['sip_username']}

[auth{data['sip_username']}]
type=auth
auth_type=userpass
username={data['sip_username']}
password={data['sip_password']}

[{data['sip_username']}]
type=aor
max_contacts=1
"""

    # Append to pjsip.conf
    with open('/etc/asterisk/pjsip.conf', 'a') as f:
        f.write(sip_config)


    # Append extension to [default] context in extensions.conf
    ext_conf_path = '/etc/asterisk/extensions.conf'
    default_context = "[default]\n"

    # Read current contents to check if [default] already exists
    with open(ext_conf_path, 'r') as f:
        content = f.read()

    with open(ext_conf_path, 'a') as f:
        if '[default]' not in content:
            f.write(f"\n{default_context}")
        f.write(f"exten => {data['sip_username']},1,Dial(PJSIP/{data['sip_username']})\n")


    # Reload Asterisk
    os.system('sudo asterisk -rx "core reload"')

    return jsonify({'message': f'SIP user {sip_username} added with context [from-internal]'})


def remove_sip_user(username):
    try:
        # Remove from pjsip.conf
        with open("/etc/asterisk/pjsip.conf", "r") as f:
            lines = f.readlines()

        new_lines = []
        skip_block = False
        for line in lines:
            if line.strip() == f"[{username}]" or line.strip() == f"[auth{username}]":
                skip_block = True
            elif line.strip().startswith("[") and skip_block:
                skip_block = False
            if not skip_block:
                new_lines.append(line)

        with open("/etc/asterisk/pjsip.conf", "w") as f:
            f.writelines(new_lines)

        # Remove from extensions.conf
        with open("/etc/asterisk/extensions.conf", "r") as f:
            ext_lines = f.readlines()

        new_ext_lines = [line for line in ext_lines if not line.strip().startswith(f"exten => {username},")]

        with open("/etc/asterisk/extensions.conf", "w") as f:
            f.writelines(new_ext_lines)

        # Reload Asterisk
        subprocess.run(["sudo", "asterisk", "-rx", "pjsip reload"])
        subprocess.run(["sudo", "asterisk", "-rx", "dialplan reload"])

    except Exception as e:
        print(f"Error removing SIP user: {e}")

@app.route('/delete_station/<telephone>', methods=['DELETE'])
def delete_station(telephone):
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT sip_username FROM stations WHERE telephone_no = %s", (telephone,))
        result = cursor.fetchone()
        sip_username = result['sip_username'] if result else None

        cursor.execute("DELETE FROM stations WHERE telephone_no = %s", (telephone,))
        conn.commit()
        cursor.close()
        conn.close()

        if sip_username:
            remove_sip_user(sip_username)

        return jsonify({"message": "Station and SIP user deleted successfully"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/hotlines', methods=['GET'])
def get_hotlines():
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM hotlines")
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return jsonify(rows)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/delete_hotline/<int:id>', methods=['DELETE'])
def delete_hotline(id):
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT hotline_extension FROM hotlines WHERE id = %s", (id,))
        row = cursor.fetchone()

        if not row:
            return jsonify({"error": "Hotline not found"}), 404

        hotline_ext = row['hotline_extension']

        # Delete from MySQL
        cursor.execute("DELETE FROM hotlines WHERE id = %s", (id,))
        conn.commit()
        cursor.close()
        conn.close()

        # Remove from extensions.conf
        with open("/etc/asterisk/extensions.conf", "r") as f:
            lines = f.readlines()

        new_lines = []
        skip_block = False
        for line in lines:
            if line.strip() == f"[hotline-{hotline_ext}]":
                skip_block = True
                continue
            if line.strip().startswith("[") and skip_block:
                skip_block = False
            if not skip_block:
                new_lines.append(line)

        with open("/etc/asterisk/extensions.conf", "w") as f:
            f.writelines(new_lines)

        subprocess.run(["sudo", "asterisk", "-rx", "dialplan reload"])
        return jsonify({"message": "Hotline deleted successfully"})

    except Exception as e:
        return jsonify({"error": str(e)}), 500
        

@app.route('/cdr', methods=['GET'])
def get_cdr_logs():
    try:
        file_path = '/var/log/asterisk/cdr-csv/Master.csv'
        logs = []
        with open(file_path, newline='') as csvfile:
            reader = csv.reader(csvfile)
            headers = next(reader)  # Skip header
            for row in list(reader)[-50:]:  # Last 50 calls
                if len(row) >= 15:
                    logs.append({
                        'calldate': row[9],
                        'src': row[1],
                        'dst': row[2],
                        'duration': row[12],
                        'disposition': row[14]
                    })
        return jsonify(logs)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/asterisk/peers')
def list_peers():
    try:
        result = subprocess.run(['sudo', 'asterisk', '-rx', 'pjsip show endpoints'], capture_output=True, text=True)
        return f"<pre>{result.stdout}</pre>"
    except Exception as e:
        return f"Error: {str(e)}", 500

@app.route('/asterisk/reload')
def reload_asterisk():
    try:
        subprocess.run(["sudo", "asterisk", "-rx", "pjsip reload"])
        subprocess.run(["sudo", "asterisk", "-rx", "dialplan reload"])
        return jsonify({"message": "Asterisk reloaded successfully"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
@app.route('/clear_cdr', methods=['POST'])
def clear_cdr():
    try:
        file_path = '/var/log/asterisk/cdr-csv/Master.csv'

        # Overwrite the file with just the headers
        with open(file_path, 'w') as f:
            f.write('"accountcode","src","dst","dcontext","clid","channel","dstchannel","lastapp","lastdata","start","answer","end","duration","billsec","disposition","amaflags","uniqueid","userfield"\n')

        return jsonify({"message": "Call logs cleared successfully."})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001)