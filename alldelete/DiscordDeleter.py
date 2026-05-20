import os, sys, json, time, requests
import codecs

# UTF-8 stdout (skip if already redirected)
try:
    if hasattr(sys.stdout, 'buffer'):
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'backslashreplace')
except:
    pass

class DiscordDeleter:
    def __init__(self):
        self.token = None
        self.bot_id = None
        
    def init_from_openclaw_config(self):
        config_path = os.path.join(os.environ.get('USERPROFILE', 'C:\\Users\\owner'), ".openclaw", "openclaw.json")
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                discord_cfg = config.get("channels", {}).get("discord", {})
                self.token = discord_cfg.get("token")
                
                url = "https://discord.com/api/v9/users/@me"
                headers = {"Authorization": f"Bot {self.token}"}
                resp = requests.get(url, headers=headers)
                if resp.status_code == 200:
                    self.bot_id = resp.json().get('id')
        return self.token
        
    def delete_message(self, channel_id, message_id):
        url = f"https://discord.com/api/v9/channels/{channel_id}/messages/{message_id}"
        headers = {"Authorization": f"Bot {self.token}"}
        try:
            response = requests.delete(url, headers=headers, timeout=10)
            
            # Handle rate limit
            if response.status_code == 429:
                retry_after = response.headers.get('retry-after', 1)
                try:
                    wait_time = float(retry_after) if retry_after else 5
                except:
                    wait_time = 5
                print(f"[RATELIMIT] Waiting {wait_time}s...", flush=True)
                time.sleep(wait_time + 1)
                # Retry once
                response = requests.delete(url, headers=headers, timeout=10)
            
            return response.status_code in [200, 204]
        except Exception as e:
            print(f"[ERROR] {e}", flush=True)
            return False
    
    def delete_all(self, channel_id):
        if not self.token:
            print("[ERROR] Discord token not found", flush=True)
            return 0
        
        deleted = 0
        batch_num = 0
        last_output = time.time()
        total_start = time.time()
        
        while True:
            url = f"https://discord.com/api/v9/channels/{channel_id}/messages?limit=100"
            headers = {"Authorization": f"Bot {self.token}"}
            
            try:
                response = requests.get(url, headers=headers, timeout=15)
                if response.status_code != 200:
                    print(f"[ERROR] Failed to fetch: {response.status_code}", flush=True)
                    break
                messages = response.json()
                if not messages:
                    elapsed = int(time.time() - total_start)
                    print(f"[DONE] No more messages. Elapsed: {elapsed}s, Deleted: {deleted}", flush=True)
                    break
            except Exception as e:
                print(f"[ERROR] Fetch failed: {e}", flush=True)
                break
            
            batch_num += 1
            msg_count = len(messages)
            
            # Progress output every 30 seconds
            elapsed = int(time.time() - total_start)
            print(f"[Batch {batch_num}] {msg_count} msgs, Total: {deleted}, Time: {elapsed}s", flush=True)
            last_output = time.time()
            
            for msg in messages:
                msg_id = msg.get('id')
                try:
                    if self.delete_message(channel_id, msg_id):
                        deleted += 1
                    else:
                        print(f"[SKIP] {msg_id}", flush=True)
                    
                    # Rate limit protection - 1.5 seconds minimum
                    time.sleep(1.5)
                    
                    # Progress every 10 deletes
                    if deleted % 10 == 0:
                        elapsed = int(time.time() - total_start)
                        print(f"[PROGRESS] {deleted} deleted, {elapsed}s elapsed", flush=True)
                        last_output = time.time()
                        
                except Exception as e:
                    print(f"[ERROR] {e}", flush=True)
                    time.sleep(3)
            
            time.sleep(2)  # Batch delay
            
            # Safety limit
            if deleted >= 10000:
                print("[LIMIT] Reached 10000 message limit", flush=True)
                break
            
            # Check if still getting messages (old messages can't be deleted)
            if msg_count == 0:
                break
        
        elapsed = int(time.time() - total_start)
        print(f"[COMPLETE] {deleted} messages deleted in {elapsed}s", flush=True)
        return deleted

def run(channel_id=None):
    print("=== Discord All Delete Started ===", flush=True)
    print(f"[TIME] {time.strftime('%Y-%m-%d %H:%M:%S')}", flush=True)
    
    deleter = DiscordDeleter()
    token = deleter.init_from_openclaw_config()
    
    if not token:
        print("[ERROR] Discord token not configured", flush=True)
        return "Error: Discord token not configured"
    
    if not channel_id:
        config_path = os.path.join(os.environ.get('USERPROFILE', 'C:\\Users\\owner'), ".openclaw", "openclaw.json")
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
            channel_id = config.get("skills", {}).get("entries", {}).get("ComfyBridge", {}).get("config", {}).get("discord_target_channel", "1498225996149817415")
    
    print(f"[INFO] Target channel: {channel_id}", flush=True)
    
    deleted = deleter.delete_all(channel_id)
    
    result = f"{deleted} messages deleted"
    print(f"[RESULT] {result}", flush=True)
    print(f"[END TIME] {time.strftime('%Y-%m-%d %H:%M:%S')}", flush=True)
    return result

if __name__ == "__main__":
    channel = sys.argv[1] if len(sys.argv) > 1 else None
    run(channel)