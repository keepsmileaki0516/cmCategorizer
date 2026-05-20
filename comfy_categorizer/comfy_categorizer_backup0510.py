import os
import sys
import json
import uuid
import requests
import socket
import subprocess
import time
import argparse

class ComfyBridge:
    def __init__(self, config_path=None):
        # 親クラス object の __init__ は引数を取らないため super() は呼び出しません
        user_profile = os.environ.get('USERPROFILE', 'C:\\Users\\owner')
        if config_path is None:
            config_path = os.path.join(user_profile, ".openclaw", "openclaw.json")
            
        self.config = {}
        self.full_config = {}
        
        # 1. JSONファイルを安全に読み込む
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        self.full_config = data
            except Exception:
                self.full_config = {}

        # 2. 辞書階層を安全にたどる補助関数 (途中に文字列があっても無視する)
        def safe_dict(d, key):
            if not isinstance(d, dict):
                return {}
            val = d.get(key, {})
            return val if isinstance(val, dict) else {}

        # 3. self.config (ComfyBridgeの設定) を安全に抽出
        # 階層を一つずつ辞書チェックしながら進みます
        skills_data = safe_dict(self.full_config, "skills")
        entries = safe_dict(skills_data, "entries")
        bridge_data = safe_dict(entries, "ComfyBridge")
        self.config = safe_dict(bridge_data, "config")

        # 4. 基本設定の反映 (辞書であることを保証してから get を実行)
        self.api_url = self.config.get("comfyui_api_url", "127.0.0.1:8188")
        self.comfy_path = self.config.get("comfy_path", "C:\\Users\\owner\\Downloads\\Data\\Packages\\ComfyUI")
        self.history_dir = self.config.get("history_dir", os.path.join(user_profile, ".openclaw", "workspace", "creative", "history"))
        self.python_exe = os.path.join(self.comfy_path, "venv", "Scripts", "python.exe")
        
        # 5. Discord情報の取得 (エラーの最大の原因箇所をガード)
        channels = safe_dict(self.full_config, "channels")
        discord = safe_dict(channels, "discord")
        # 最後の値は辞書ではないため個別にチェック
        self.discord_token = discord.get("token") if isinstance(discord, dict) else None
        
        self.target_channel = self.config.get("discord_target_channel", "1498225996149817415")

        # 6. ディレクトリ作成と起動確認
        os.makedirs(self.history_dir, exist_ok=True)
        self.ensure_comfyui_running()

    def is_process_running(self):
        try:
            out = subprocess.check_output(['tasklist'], text=True)
            return 'comfyui' in out.lower() or 'main.py' in out.lower()
        except Exception:
            return False

    def ensure_comfyui_running(self):
        host, port = self.api_url.split(':')
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(2)
            if s.connect_ex((host, int(port))) == 0:
                return

        if not os.path.isdir(self.comfy_path):
            possible_paths = [
                os.path.join(os.environ.get('USERPROFILE', ''), 'Downloads', 'Data', 'Packages', 'ComfyUI'),
                os.path.join(os.environ.get('USERPROFILE', ''), 'AppData', 'Local', 'StabilityMatrix', 'Packages', 'ComfyUI'),
            ]
            for p in possible_paths:
                if os.path.isdir(p):
                    self.comfy_path = p
                    break
            else:
                print(f"[ComfyBridge] Error: ComfyUI folder not found.")
                return

        self.python_exe = os.path.join(self.comfy_path, 'venv', 'Scripts', 'python.exe')
        
        if not os.path.isfile(self.python_exe):
            print(f"[ComfyBridge] Error: venv Python not found: {self.python_exe}")
            return

        try:
            print(f"[ComfyBridge] Launching ComfyUI: {self.comfy_path}")
            CREATE_NO_WINDOW = 0x08000000
            subprocess.Popen(
                [self.python_exe, 'main.py'],
                cwd=self.comfy_path,
                creationflags=CREATE_NO_WINDOW,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        except Exception as e:
            print(f"[ComfyBridge] Launch failed: {e}")
            return

        print("[ComfyBridge] Waiting for API...")
        for attempt in range(30):
            time.sleep(2)
            try:
                resp = requests.get(f"http://{self.api_url}/object_info", timeout=2)
                if resp.status_code == 200:
                    print("[ComfyBridge] API online!")
                    return
            except:
                pass
            print(f"Waiting... ({attempt + 1}/30)")
            
        print("[ComfyBridge] Warning: Timeout. ComfyUI may not be running correctly.")

    def get_latest_history(self):
        if not os.path.exists(self.history_dir): return {}
        files = [f for f in os.listdir(self.history_dir) if f.startswith('info') and f.endswith('.json')]
        if not files: return {}
        latest_file = max([os.path.join(self.history_dir, f) for f in files], key=os.path.getmtime)
        
        with open(latest_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        # UI形式(nodes/linksあり)をAPI形式に完全復元
        if isinstance(data, dict) and "nodes" in data and "links" in data:
            link_map = {l[0]: [str(l[1]), l[2]] for l in data.get("links", []) if l}
            api_format = {}
            for node in data["nodes"]:
                nid, ntype = str(node.get("id")), node.get("type")
                api_format[nid] = {"class_type": ntype, "inputs": {}, "_is_ui_format": True, "_ui_node": node}
                
                # 線(リンク)の接続を復元
                for inp in node.get("inputs", []):
                    l_id = inp.get("link")
                    if l_id in link_map: api_format[nid]["inputs"][inp["name"]] = link_map[l_id]
                
                # 設定値(ウィジェット)を復元
                w = node.get("widgets_values", [])
                if not isinstance(w, list): w = []
                mapping = {
                    "DualPromptEncoder": {"name": 0, "positive": 1, "negative": 2},
                    "CheckpointLoaderSimple": {"ckpt_name": 0},
                    "LoraLoader": {"lora_name": 0, "strength_model": 1, "strength_clip": 2},
                    "EmptyLatentImage": {"width": 0, "height": 1, "batch_size": 2},
                    "KSampler": {"seed": 0, "steps": 2, "cfg": 3, "sampler_name": 4, "scheduler": 5, "denoise": 6},
                    "KSamplerAdvanced": {"seed": 0, "steps": 2, "cfg": 3, "sampler_name": 4, "scheduler": 5, "denoise": 6},
                    "LatentUpscale": {"upscale_method": 0, "width": 1, "height": 2, "crop": 3},
                    "SaveImage": {"filename_prefix": 0}
                }
                if ntype in mapping:
                    for key, idx in mapping[ntype].items():
                        if len(w) > idx: api_format[nid]["inputs"][key] = w[idx]
            return api_format
        return data

    def wait_for_final_image(self, prompt_id, workflow):
        save_nodes = [nid for nid, node in workflow.items() if node.get("class_type") == "SaveImage"]
        if not save_nodes: return None
        
        # 最もIDが大きい（最後に実行される）SaveImageノードをターゲットにする
        try:
            target_node = max(save_nodes, key=lambda x: int(x))
        except Exception:
            target_node = sorted(save_nodes)[-1]

        print(f"[ComfyBridge] Waiting for image (ID: {prompt_id})...")
        
        # 待機時間を延長 (2秒 * 300回 = 最大10分間待機)
        for attempt in range(300): 
            time.sleep(2)
            try:
                # 実行中・待機中キューの確認
                q = requests.get(f"http://{self.api_url}/queue", timeout=3).json()
                active = [item[1] for item in q.get("queue_running", []) + q.get("queue_pending", [])]
                
                # 履歴の確認
                h_resp = requests.get(f"http://{self.api_url}/history/{prompt_id}", timeout=3)
                if h_resp.status_code == 200:
                    history = h_resp.json()
                    if prompt_id in history:
                        h_item = history[prompt_id]
                        
                        # エラーチェック
                        if "status" in h_item and "messages" in h_item["status"]:
                            for msg in h_item["status"]["messages"]:
                                if msg[0] == "execution_error":
                                    err = msg[1]
                                    raise Exception(f"Node {err.get('node_id')}: {err.get('exception_message')}")
                        
                        # 出力画像の取得
                        outputs = h_item.get("outputs", {})
                        if target_node in outputs:
                            img = outputs[target_node]["images"][0]
                            full_path = os.path.join(self.comfy_path, "output", img.get("subfolder", ""), img["filename"])
                            print(f"[ComfyBridge] Image found: {full_path}")
                            return full_path

                # キューからも履歴からも消えた場合は異常終了
                if prompt_id not in active and attempt > 5: # 開始直後のラグを考慮
                    # 履歴を再確認して本当になければエラー
                    h_resp_final = requests.get(f"http://{self.api_url}/history/{prompt_id}", timeout=3)
                    if prompt_id not in h_resp_final.json():
                        raise Exception("Task disappeared from queue without history.")

            except Exception as e:
                if "disappeared" in str(e) or "Node" in str(e): 
                    print(f"[ComfyBridge] Error during wait: {e}")
                    raise e
            
            if attempt % 5 == 0:
                print(f"Still processing... ({attempt}/300)")
                
        raise TimeoutError("Timed out waiting for image generation.")

    def run(self, modifications=None, send_discord=False, target_num=None, workflow_type='default'):
        try:
            if modifications is not None:
                # 親クラスのComfyBridge.runを呼び出すのではなく、
                # 直接ロジックを書き直してDiscord送信を確実にします
                current_workflow = self.get_latest_history()
                new_workflow = json.loads(json.dumps(current_workflow))
                
                if modifications:
                    for nid, content in modifications.items():
                        if nid in new_workflow:
                            node = new_workflow[nid]
                            if "inputs" not in node: node["inputs"] = {}
                            node["inputs"].update(content.get("inputs", {}))
                            if "widgets_values" in content and "_ui_node" in node:
                                node["_ui_node"]["widgets_values"] = content["widgets_values"]

                clean_prompt = {}
                for nid, data in new_workflow.items():
                    clean_prompt[nid] = {
                        "class_type": data.get("class_type"),
                        "inputs": data.get("inputs", {})
                    }
                
                p = {"prompt": clean_prompt, "client_id": str(uuid.uuid4())}
                res = requests.post(f"http://{self.api_url}/prompt", json=p, timeout=5)
                if res.status_code != 200: return f"API Error: {res.text}"
                
                prompt_id = res.json().get("prompt_id")
                self.save_to_history(new_workflow)
                
                if send_discord:
                    image_path = self.wait_for_final_image(prompt_id, new_workflow)
                    if image_path and os.path.exists(image_path):
                        self.send_to_discord(image_path) # Discordへ送信
                        return f"Success: {image_path}"
                    return "Error: Image path not found."
                return "Success (no discord)"

            # 以降、target_num等の処理（既存のまま）
            if target_num is not None:
                return self._replay_history_item(target_num)
            else:
                return self._fetch_and_process_new(workflow_type)
                
        except Exception as e:
            return f"Execution Error: {e}"

    def send_to_discord(self, image_path):
        if not self.discord_token: return
        url = f"https://discord.com/api/v10/channels/{self.target_channel}/messages"
        headers = {"Authorization": f"Bot {self.discord_token}"}
        try:
            with open(image_path, "rb") as f:
                requests.post(url, headers=headers, data={"content": "Generated Image"}, files={"file": f}, timeout=15)
        except: pass

    def save_to_history(self, workflow_json):
        import datetime
        timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        path = os.path.join(self.history_dir, f"info{timestamp}_01.json")
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(workflow_json, f, indent=2, ensure_ascii=False)

    def get_workflow_info(self):
        try:
            wf = self.get_latest_history()
            if not wf: return "No history found."
            lines = ["--- Nodes ---"]
            for nid, data in wf.items():
                lines.append(f"Node [{nid}]: {data.get('class_type')}")
            return "\n".join(lines)
        except Exception as e: return f"Error: {e}"


class ComfyCategorizer(ComfyBridge):
    CATEGORY_FILES = ["background.txt", "body.txt", "clothing.txt", "head.txt", "limbs.txt", "nsfw.txt", "pose.txt", "quality.txt"]
    
    def __init__(self, config_path=None, dictionary_path=None):
        super().__init__(config_path)
        
        # ImageSampler settings
        self.api_key = "79c5cfb935ca50358b15cb931cfe9bb5"
        self.tag = "female"
        self.exclude_keywords = "man penis"
        self.browsing_level = 16
        self.history_file = os.path.join(os.path.dirname(__file__), "processed_urls.txt")
        
        base_path = os.path.dirname(__file__)
        if dictionary_path is None:
            dictionary_path = os.path.join(base_path, "categorized_prompts")
        
        self.dictionary_path = dictionary_path
        self.unclassified_path = os.path.join(base_path, "categorized_prompts", "unclassified.txt")
        self.settings_path = os.path.join(os.path.dirname(__file__), "workflow_settings.json")
        
        self.dictionaries = {}
        self.categories = {
            "all": [], "head": [], "body": [], "clothing": [], "limbs": [],
            "pose": [], "quality": [], "background": [], "nsfw": []
        }
        
        self.load_dictionaries()
        self.load_settings()
    
    def load_dictionaries(self):
        for filename in self.CATEGORY_FILES:
            filepath = os.path.join(self.dictionary_path, filename)
            if os.path.exists(filepath):
                category = filename.replace(".txt", "")
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        words = [line.strip() for line in f if line.strip()]
                        self.dictionaries[category] = set(words)
                        self.categories[category] = []
                except Exception:
                    pass  # エラーが起きても止まらずに次のファイルへ進む
    
    def load_settings(self):
        self.settings = {}
        if os.path.exists(self.settings_path):
            try:
                with open(self.settings_path, 'r', encoding='utf-8') as f:
                    self.settings = json.load(f)
            except Exception:
                pass
    
    def categorize_prompt(self, prompt):
        """Categorize prompt by splitting on comma, cleaning words, and matching against dictionaries.
        
        Word cleaning process:
        1. Strip whitespace
        2. Discard LoRA tags (<...>)
        3. Remove parentheses ()
        4. Remove weights (everything after :)
        
        Matching uses clean_word, but original word is preserved in categories.
        """
        if not prompt or not prompt.strip():
            return {"error": "empty_prompt"}
        
        # Reset all categories
        for cat in self.categories:
            self.categories[cat] = []
        
        unclassified = []
        seen_unclassified = set()  # For duplicate checking using clean_word
        
        words = [w.strip() for w in prompt.split(",")]
        
        for word in words:
            # Skip empty strings
            if not word or word.isspace():
                continue
            
            # === WORD CLEANING FOR MATCHING ===
            clean_word = word
            
            # Step 1: Already stripped above (done during split)
            
            # Step 2: Discard LoRA tags (<...>)
            if clean_word.startswith("<") and clean_word.endswith(">"):
                continue
            
            # Step 3: Remove all ( and )
            clean_word = clean_word.replace("(", "").replace(")", "")
            
            # Step 4: If contains ':', remove it and everything after
            if ":" in clean_word:
                clean_word = clean_word.split(":")[0]
            
            # Skip if clean_word is empty after processing
            if not clean_word or clean_word.isspace():
                continue
            
            # Convert to lowercase for dictionary matching
            clean_word_lower = clean_word.lower()
            
            # === DICTIONARY MATCHING ===
            matched = False
            for category, dict_set in self.dictionaries.items():
                if clean_word_lower in dict_set:
                    # 原文をカテゴリに追加
                    original_stripped = word.strip()
                    self.categories[category].append(original_stripped)

                    # nsfw以外なら 'all' カテゴリにも即座に追加
                    if category != "nsfw":
                        self.categories["all"].append(original_stripped)

                    matched = True
                    break
            
            # === UNCLASSIFIED HANDLING ===
            if not matched:
                clean_for_unclassified = clean_word_lower
                if clean_for_unclassified and clean_for_unclassified not in seen_unclassified:
                    unclassified.append(clean_word)  # Use clean_word for file
                    seen_unclassified.add(clean_for_unclassified)
                    self.categories["all"].append(word.strip())
        
        self.save_unclassified(unclassified)
        
        return {
            "categories": self.categories,
            "nsfw_filtered": list(self.categories.get("nsfw", [])),
            "unclassified": unclassified
        }
    
    def save_unclassified(self, words):
        if not words:
            return
        
        existing = set()
        if os.path.exists(self.unclassified_path):
            try:
                with open(self.unclassified_path, 'r', encoding='utf-8') as f:
                    existing = set(line.strip() for line in f if line.strip())
            except Exception:
                pass
        
        new_words = [w for w in words if w not in existing]
        
        if new_words:
            try:
                with open(self.unclassified_path, 'a', encoding='utf-8') as f:
                    for w in new_words:
                        f.write(w + "\n")
            except Exception:
                pass
    
    def get_clean_prompt(self, prompt):
        result = self.categorize_prompt(prompt)
        
        clean_parts = []
        for cat, items in result["categories"].items():
            if cat != "nsfw":
                clean_parts.extend(items)
        
        if not clean_parts:
            return prompt
        
        return ", ".join(clean_parts)
    
    def get_divided_prompt(self, prompt):
        result = self.categorize_prompt(prompt)
        return result["categories"]
    
    def get_nsfw_words(self, prompt):
        result = self.categorize_prompt(prompt)
        return result.get("nsfw_filtered", [])
    
    def remove_nsfw_from_prompt(self, prompt):
        result = self.categorize_prompt(prompt)
        
        clean_parts = []
        for cat, items in result["categories"].items():
            if cat != "nsfw":
                clean_parts.extend(items)
        
        return ", ".join(clean_parts) if clean_parts else ""
    
    def get_dual_prompt_encoder_nodes(self, workflow):
        dual_nodes = []
        if not isinstance(workflow, dict): return []
        
        for nid, node in workflow.items():
            if not isinstance(node, dict): continue
            
            if node.get("class_type") == "DualPromptEncoder":
                inputs = node.get("inputs", {})
                # UI形式とAPI形式の両方から名前を取得
                node_title = inputs.get("name", "") or node.get("title", "")
                
                dual_nodes.append({
                    "node_id": nid,
                    "title": node_title,
                    "node_data": node
                })
        return dual_nodes
    
    def get_node_mapping(self, workflow_type="default"):
        settings = self.settings.get("workflow_types", {}).get(workflow_type, {})
        base_mapping = settings.get("node_category_mapping", {})
        
        # Expand comma-separated keys into individual entries
        expanded_mapping = {}
        for key, value in base_mapping.items():
            if "," in key:
                # Split comma-separated names and create entries for each part
                parts = [p.strip() for p in key.split(",")]
                for part in parts:
                    if part:
                        expanded_mapping[part] = value
            else:
                expanded_mapping[key] = value
        
        return expanded_mapping
    
    def get_safe_prompt_for_node(self, category_name):
        # Handle "all" special case: return full clean prompt (all categories combined EXCEPT nsfw)
        if category_name == "all":
            clean_parts = []
            for cat, items in self.categories.items():
                if cat != "nsfw":
                    clean_parts.extend(items)
            # Strip whitespace from each element before joining
            return ", ".join([p.strip() for p in clean_parts if p.strip()])
        
        # Get words for the specific category and strip whitespace
        items = [item.strip() for item in self.categories.get(category_name, []) if item.strip()]
        return ", ".join(items)
    
    # --- ImageSampler integration methods ---
    
    def _send_direct_discord_message(self, content):
        """Discord API v10 を使用して直接メッセージを送信する"""
        if not self.discord_token or not self.target_channel:
            return
        
        url = f"https://discord.com/api/v10/channels/{self.target_channel}/messages"
        headers = {
            "Authorization": f"Bot {self.discord_token}",
            "Content-Type": "application/json"
        }
        payload = {"content": content}
        
        try:
            response = requests.post(url, headers=headers, json=payload)
            if response.status_code != 200:
                print(f"Discord API Error: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"Discord Connection Error: {e}")

    def _get_all_records(self):
        if not os.path.exists(self.history_file):
            return []
        records = []
        with open(self.history_file, 'r', encoding='utf-8') as f:
            for line in f:
                parts = line.strip().split(',')
                if len(parts) >= 2:
                    records.append((parts[0], parts[1]))
        return records

    def _get_processed_page_urls(self):
        if not os.path.exists(self.history_file):
            return set()
        with open(self.history_file, 'r', encoding='utf-8') as f:
            return {line.strip().split(',')[0] for line in f if line.strip()}

    def _get_processed_count(self):
        return len(self._get_all_records())

    def _save_processed(self, page_url, post_id):
        with open(self.history_file, 'a', encoding='utf-8') as f:
            f.write(f"{page_url},{post_id}\n")

    def _fetch_item_by_post_id(self, post_id):
        api_url = f"https://civitai.com/api/v1/images?postId={post_id}&browsingLevel=31"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        try:
            response = requests.get(api_url, headers=headers)
            if response.status_code == 200:
                items = response.json().get('items', [])
                for item in items:
                    if str(item.get('postId')) == str(post_id):
                        return item
        except:
            pass
        return None
    
    # --- Overridden draw with categorizer logic ---

    def draw(self, prompt, neg="", seed=-1, node_id=None, workflow_type="default"):
        current_workflow = self.get_latest_history()
        if not current_workflow: return "Error: No history found."
        
        # 1. プロンプトを仕分け
        self.categorize_prompt(prompt)
        
        mods = {}
        lock_path = os.path.join(os.path.dirname(__file__), "seedrandom.lock")
        target_seed = 0 if os.path.exists(lock_path) else (seed if seed != -1 else None)
        AUTO_TEXT_KEYS = {"text", "positive", "negative", "pos_display", "neg_display", "in_positive"}
        
        dual_nodes = self.get_dual_prompt_encoder_nodes(current_workflow)
        node_mapping = self.get_node_mapping(workflow_type) if dual_nodes else {}
        
        # 2. DualPromptEncoder ノードの書き換え
        for node_info in dual_nodes:
            nid = node_info["node_id"]
            node = node_info["node_data"]
            node_title = node_info["title"]
            inputs = node.get("inputs", {}) or {}
            
            # カンマ区切り（all,nsfwなど）を分解
            title_parts = [p.strip().lower() for p in node_title.split(",")]
            final_prompts = []
            
            for part in title_parts:
                if part in self.categories and self.categories[part]:
                    final_prompts.append(", ".join(self.categories[part]))
                elif part in node_mapping:
                    target_cat = node_mapping[part]
                    if target_cat == "all":
                        if self.categories.get("all"):
                            final_prompts.append(", ".join(self.categories["all"]))
                    else:
                        items = self.categories.get(target_cat, [])
                        if items:
                            final_prompts.append(", ".join(items))

            # 結合
            positive_prompt = ", ".join(dict.fromkeys(final_prompts))
            # 空ならフォールバック
            if not positive_prompt.strip():
                positive_prompt = prompt

            negative_prompt = neg.strip() if neg else "low quality, worst quality"
            
            if nid not in mods:
                mods[nid] = {"inputs": {}}

            # UI形式とAPI形式の両方を確実に更新
            if node.get("_is_ui_format"):
                ui_node = node.get("_ui_node", {})
                w = list(ui_node.get("widgets_values", []))
                if len(w) >= 3:
                    w[0], w[1], w[2] = node_title, positive_prompt, negative_prompt
                    mods[nid]["widgets_values"] = w
                
                # API実行用 inputs も同期
                mods[nid]["inputs"].update({
                    "positive": positive_prompt,
                    "negative": negative_prompt,
                    "name": node_title
                })
            else:
                for key in ["text", "positive", "in_positive"]:
                    if key in inputs: mods[nid]["inputs"][key] = positive_prompt
                for key in ["negative", "neg_display"]:
                    if key in inputs: mods[nid]["inputs"][key] = negative_prompt
                mods[nid]["inputs"]["name"] = node_title

        # 3. その他のノードの汎用処理
        for nid, node in current_workflow.items():
            if node.get("class_type") == "DualPromptEncoder": continue
            node_mods = {}
            for k, v in node.get("inputs", {}).items():
                if k in AUTO_TEXT_KEYS and isinstance(v, str):
                    if any(x in v.lower() for x in ["neg", "bad", "worst"]):
                        node_mods[k] = negative_prompt
                    else:
                        node_mods[k] = positive_prompt if positive_prompt else prompt
                elif k == "seed" and target_seed is not None:
                    node_mods[k] = target_seed
            if node_mods:
                if nid not in mods: mods[nid] = {"inputs": {}}
                mods[nid]["inputs"].update(node_mods)
        
        # 4. 実行メソッドの呼び出し
        return self.run(modifications=mods, send_discord=True)

    def run(self, modifications=None, send_discord=False, target_num=None, workflow_type='default'):
        try:
            # draw() からの修正依頼がある場合
            if modifications is not None:
                # 【修正の核心】 super().run に self を渡さない
                return super().run(modifications=modifications, send_discord=send_discord)

            # CLI からの直接実行
            if target_num is not None:
                return self._replay_history_item(target_num)
            else:
                return self._fetch_and_process_new(workflow_type)
        except Exception as e:
            return f"Execution Error: {e}"
    
    def _replay_history_item(self, target_num):
        """Replay a specific item from processed_urls.txt history."""
        records = self._get_all_records()
        if not (1 <= target_num <= len(records)):
            return f"Error: 1から{len(records)}までの数値を指定してください。"
        
        page_url, post_id = records[target_num - 1]
        item = self._fetch_item_by_post_id(post_id)
        
        if not item or 'meta' not in item:
            return f"Error: {target_num}件目のデータが取得できませんでした。"
        
        meta = item.get('meta')
        image_direct_url = item.get('url')
        prompt = meta.get('prompt', '')
        neg_prompt = meta.get('negativePrompt', '')
        
        # Log unclassified words before generation
        self.categorize_prompt(prompt)
        
        # Use legacy draw (no DualPromptEncoder check) for replay
        # Use the categorizer's draw method to generate the image with proper prompt handling
        result = self.draw(prompt=prompt, neg=neg_prompt)
        
        if "Success" in result:
            self._send_direct_discord_message(f"[{target_num}件目]({image_direct_url})")
        
        return f"[{target_num}件目の履歴を再生成]({image_direct_url})"
    
    def _fetch_and_process_new(self, workflow_type='default'):
        """Fetch new items from Civitai API and process them."""
        processed_urls = self._get_processed_page_urls()
        api_url = f"https://civitai.com/api/v1/images?tag={self.tag}&limit=100&sort=Newest&browsingLevel={self.browsing_level}&withMeta=true"
        headers = {"Authorization": f"Bearer {self.api_key}"}

        while api_url:
            response = requests.get(api_url, headers=headers)
            if response.status_code != 200:
                return f"API Error: {response.status_code}"
            
            data = response.json()
            for item in data.get('items', []):
                post_id = item.get('postId')
                page_url = f"https://civitai.com/images/{post_id}"
                image_direct_url = item.get('url')
                
                if page_url in processed_urls:
                    continue
                
                meta = item.get('meta')
                if not meta or 'prompt' not in meta:
                    self._save_processed(page_url, post_id)
                    continue
                
                prompt_text = meta.get('prompt', "").lower()
                exclude_list = self.exclude_keywords.lower().split()
                if any(kw in prompt_text for kw in exclude_list):
                    continue
                
                prompt = meta.get('prompt', '')
                neg_prompt = meta.get('negativePrompt', '')
                
                # Categorize prompt and log unclassified words before generation
                self.categorize_prompt(prompt)
                
                # Use categorizer draw method
                result = self.draw(prompt=prompt, neg=neg_prompt, workflow_type=workflow_type)
                
                if "Success" in result:
                    self._save_processed(page_url, post_id)
                    count = self._get_processed_count()
                    self._send_direct_discord_message(f"[{count}件目]({image_direct_url})")
                    return f"[{count}件目に新規登録]({image_direct_url})"
                else:
                    # Generation failed - do NOT save, return error
                    return f"Generation Error: {result}"
            
            api_url = data.get('metadata', {}).get('nextPage')
        return "Error: No new items found."
    
    def get_error_test_suggestion(self):
        return """
Minimal test script:
```
import os, json
from comfy_categorizer import ComfyCategorizer

cc = ComfyCategorizer()
test_prompt = "1girl, beautiful, red hair, standing"

print("Dictionaries loaded:", list(cc.dictionaries.keys()))
print("Categories:", cc.categories)

result = cc.categorize_prompt(test_prompt)
print("Result:", result)
```
"""
    
    def execute(self, prompt, workflow=None, workflow_type="default"):
        try:
            if workflow is None:
                workflow = self.get_latest_history()
                if not workflow:
                    return {"error": "no_history"}
            
            self.categorize_prompt(prompt)
            
            clean_prompt = self.remove_nsfw_from_prompt(prompt)
            
            dual_nodes = self.get_dual_prompt_encoder_nodes(workflow)
            
            if not dual_nodes:
                return {"mode": "legacy", "prompt": clean_prompt, "original": prompt}
            
            node_mapping = self.get_node_mapping(workflow_type)
            
            node_prompts = {}
            for node_info in dual_nodes:
                node_title = node_info["title"]
                # カンマ区切りのタイトルを分解 (例: "all,nsfw")
                title_parts = [p.strip().lower() for p in node_title.split(",")]
                
                final_parts = []
                for part in title_parts:
                    # 1. 直接カテゴリ名として存在するか確認
                    if part in self.categories:
                        items = self.categories[part]
                        if items:
                            final_parts.append(", ".join(items))
                    
                    # 2. workflow_settings.json のマッピングを確認
                    elif part in node_mapping:
                        target_cat = node_mapping[part]
                        # all の場合は全取得、それ以外は特定カテゴリ取得
                        p = self.get_safe_prompt_for_node(target_cat)
                        if p:
                            final_parts.append(p)

                # 重複を避けて結合
                prompt_to_use = ", ".join(dict.fromkeys(final_parts))
                
                # もし空なら元のプロンプトをフォールバック
                if not prompt_to_use.strip():
                    prompt_to_use = prompt
                    
                node_prompts[node_info["node_id"]] = prompt_to_use
            return {
                "mode": "dual",
                "node_prompts": node_prompts,
                "categories": self.categories,
                "nsfw_detected": len(self.categories.get("nsfw", [])) > 0,
                "unclassified": self.categories.get("unclassified", [])
            }
        
        except Exception:
            error_count = getattr(self, 'error_count', 0) + 1
            self.error_count = error_count
            
            if error_count >= 3:
                self.error_count = 0
                return {
                    "error": "repeated_failure",
                    "suggestion": self.get_error_test_suggestion()
                }
            
            return {"error": "execution_failed"}


# --- CLI entry point ---

if __name__ == "__main__":
    cc = ComfyCategorizer()
    
    target_num = None
    workflow_type = 'default'
    
    if len(sys.argv) > 1:
        first_arg = sys.argv[1]
        
        # Parse format: "5" or "5,detailed"
        if first_arg.isdigit():
            target_num = int(first_arg)
        elif ',' in first_arg:
            parts = first_arg.split(',')
            if parts[0].isdigit():
                target_num = int(parts[0])
            if len(parts) > 1:
                workflow_type = parts[1].strip()
        else:
            # Try parsing as workflow_type only (no target_num)
            workflow_type = first_arg
    
    # Run the full pipeline: fetch prompt (or replay), generate image, send Discord
    result = cc.run(target_num=target_num, workflow_type=workflow_type)
    print("Result:", result)
