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

    def run(self, modifications=None, send_discord=False, target_num=None, workflow_type='default', workflow=None):
        try:
            if modifications is not None:
                # workflow が明示的に指定されていればそれを使用、なければ history から取得
                if workflow is None:
                    workflow = self.get_latest_history()
                new_workflow = json.loads(json.dumps(workflow))
                
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
                    node = {
                        "class_type": data.get("class_type"),
                        "inputs": data.get("inputs", {})
                    }
                    # API形式のみに限定（_is_ui_format / _ui_node をstrip）
                    clean_prompt[nid] = node
                
                p = {"prompt": clean_prompt, "client_id": str(uuid.uuid4())}
                res = requests.post(f"http://{self.api_url}/prompt", json=p, timeout=5)
                if res.status_code != 200: return f"API Error: {res.text}"
                
                prompt_id = res.json().get("prompt_id")
                
                # output_enabled が True の場合のみ history を保存
                # 現在の active_workflow の設定を参照
                settings = getattr(self, 'settings', {})
                active_wf = getattr(self, 'active_workflow', 'default')
                wf_config = settings.get("workflow_types", {}).get(active_wf, {}) if isinstance(settings, dict) else {}
                output_enabled = wf_config.get("output_enabled", True) if isinstance(wf_config, dict) else True
                if output_enabled:
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
    CATEGORY_FILES = ["blacklist.txt", "background.txt", "body.txt", "clothing.txt", "head.txt", "limbs.txt", "nsfw.txt", "pose.txt", "quality.txt"]
    
    # __file__ が解決不能なケースに対応（クラス定義時に絶対パスで解決）
    _BASE_PATH = os.path.dirname(os.path.abspath(__file__))
    
    def __init__(self, config_path=None, dictionary_path=None):
        super().__init__(config_path)
        
        # ImageSampler settings
        self.api_key = "79c5cfb935ca50358b15cb931cfe9bb5"
        self.tag = "female"
        self.exclude_keywords = "man penis"
        self.browsing_level = 16
        self.history_file = os.path.join(ComfyCategorizer._BASE_PATH, "processed_urls.txt")
        
        base_path = ComfyCategorizer._BASE_PATH
        if dictionary_path is None:
            dictionary_path = os.path.join(base_path, "categorized_prompts")
        
        self.dictionary_path = dictionary_path
        self.unclassified_path = os.path.join(base_path, "categorized_prompts", "unclassified.txt")
        self.settings_path = os.path.join(base_path, "workflow_settings.json")
        
        self.dictionaries = {}
        self.categories = {
            "all": [], "head": [], "body": [], "blacklist": [], "clothing": [], "limbs": [],
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
        
        # 安全ガード: self.settings が万が一辞書でなければ強制的に空の辞書にする
        if not isinstance(self.settings, dict):
            self.settings = {}
        
        # active_workflow を取得
        self.active_workflow = self.settings.get("active_workflow", "default")
        
        # active_workflow の設定を直接一括ロード
        active_config = self.settings.get("workflow_types", {}).get(self.active_workflow, {})
        
        # 安全ガード: active_config が辞書（dict）でない場合は空の辞書にする
        if not isinstance(active_config, dict):
            active_config = {}
        
        self.workflowfile = active_config.get("workflowfile", "")
        self.output_enabled = active_config.get("output_enabled", True)
        self.nodes_by_name = active_config.get("nodes_by_name", {})
        self.nodes_by_id = active_config.get("nodes_by_id", {})
        
        # draw からの呼び出し時、force_save フラグが立っていれば detailed を保存
        if getattr(self, '_save_workflow_after_load', False):
            self._save_workflow_after_load = False
            self._save_active_workflow()
    
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
        
        clean_prompt = prompt.replace("\\", "")
        words = [w.strip() for w in clean_prompt.split(",")]
        
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
            clean_word = clean_word.replace("(", "").replace(")", "").strip()
            clean_word = clean_word.replace("[", "").replace("]", "").strip()
            clean_word = clean_word.translate(str.maketrans("", "", "0123456789")).strip()
            
            # === NEW: 複合語の末尾マッチング（ハイフンやスペース対応） ===
            # "waist-length-hair" や "blue eyes" の場合、最後の "hair" や "eyes" だけを抽出
            if "-" in clean_word or " " in clean_word:
                # ハイフンをスペースに統一してから分割し、最後の単語を取得
                clean_word = clean_word.replace("-", " ").split()[-1]
            
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

                    # nsfw / blacklist 以外なら 'all' カテゴリにも即座に追加
                    if category not in ("nsfw", "blacklist"):
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

    def draw(self, prompt, neg="", seed=-1, node_id=None, workflow_type=None):
        #self.debug_print_categorization(prompt, neg)
        
        # 1. 引数で明示的にワークフローが指定された場合、アクティブワークフローを切り替える
        if workflow_type is not None and workflow_type != self.active_workflow:
            settings_path = os.path.join(ComfyCategorizer._BASE_PATH, "workflow_settings.json")
            wf_check = {}
            if os.path.exists(settings_path):
                with open(settings_path, 'r', encoding='utf-8') as f:
                    wf_check = json.load(f).get("workflow_types", {})
            
            if workflow_type not in wf_check:
                raise ValueError(f"Workflow type '{workflow_type}' not found. Available: {list(wf_check.keys())}")
            
            # アクティブな設定名を上書き
            self.active_workflow = workflow_type
            # 変更を workflow_settings.json に即座に保存
            self._save_active_workflow()
            # 保存した最新の設定から workflowfile やノードマップなどを再読み込み
            self.load_settings()
        
        # 2. 正しくロードされた self.workflowfile からワークフローファイルを読み込む
        if self.workflowfile:
            wf_path = os.path.join(ComfyCategorizer._BASE_PATH, "workflows", self.workflowfile)
            if not os.path.exists(wf_path):
                raise FileNotFoundError(f"Workflow file not found: {wf_path}")
            try:
                with open(wf_path, 'r', encoding='utf-8') as f:
                    current_workflow = json.load(f)
                print(f"[ComfyCategorizer] Loaded workflow: {self.workflowfile}")
            except json.JSONDecodeError as e:
                raise ValueError(f"Failed to parse workflow JSON ({wf_path}): {e}")
        else:
            current_workflow = self.get_latest_history()
            print(f"[ComfyCategorizer] Loaded workflow: history (no workflowfile configured)")
        
        if not current_workflow: return "Error: No history found."
        
        # 1. プロンプトを仕分け
        self.categorize_prompt(prompt)
        
        mods = {}
        lock_path = os.path.join(ComfyCategorizer._BASE_PATH, "seedrandom.lock")
        target_seed = 0 if os.path.exists(lock_path) else (seed if seed != -1 else None)
        
        # nodes_by_name と nodes_by_id は load_settings で既に設定済み
        
        # 2. nodes_by_name に基づいてノードを書き換え
        for node_info in self.get_dual_prompt_encoder_nodes(current_workflow):
            nid = node_info["node_id"]
            node = node_info["node_data"]
            node_title = node_info["title"]
            inputs = node.get("inputs", {}) or {}
            
            # nodes_by_name の positive / negative を検索
            positive_config = self.nodes_by_name.get("positive", {}).get(node_title, {})
            negative_config = self.nodes_by_name.get("negative", {}).get(node_title, {})
            
            # === Positive プロンプトの構築 ===
            positive_prompt = ""
            assign = positive_config.get("assign")
            
            if isinstance(assign, str):
                # カンマ区切りのカテゴリの場合
                assign_cats = assign.split(",")
                parts = []
                for cat in assign_cats:
                    cat = cat.strip()
                    if cat == "all":
                        # all: nsfw以外，全カテゴリを結合
                        for c, items in self.categories.items():
                            if c not in ("nsfw", "blacklist"):
                                parts.extend([item.strip() for item in items if item.strip()])
                    elif cat == "nsfw":
                        parts.extend([item.strip() for item in self.categories.get("nsfw", []) if item.strip()])
                    else:
                        parts.extend([item.strip() for item in self.categories.get(cat, []) if item.strip()])
                
                # 重複を許可して結合（set や dict.fromkeys を使用しない）
                positive_prompt = ", ".join(parts) if parts else positive_config.get("default", "")
            
            # 全ての指定カテゴリが空の場合は default の値を使用
            if not positive_prompt.strip():
                positive_prompt = positive_config.get("default", "")
            
            # それでも空なら元のプロンプトを使用
            if not positive_prompt.strip():
                positive_prompt = prompt
            
            # === Negative プロンプトの構築 ===
            neg_assign = negative_config.get("assign")
            
            if neg_assign is True or (isinstance(neg_assign, str) and neg_assign.lower() == "true"):
                # assign: true の場合は引数で渡された neg をそのまま使用
                negative_prompt = neg.strip() if neg else negative_config.get("default", "")
            elif isinstance(neg_assign, str) and neg_assign:
                # 文字列（"all", "head" 等）の場合はカテゴリ抽出ロジックを適用（重複許可）
                neg_cats = neg_assign.split(",")
                neg_parts = []
                for cat in neg_cats:
                    cat = cat.strip()
                    if cat == "all":
                        # all: nsfw以外，全カテゴリを結合
                        for c, items in self.categories.items():
                            if c not in ("nsfw", "blacklist"):
                                neg_parts.extend([item.strip() for item in items if item.strip()])
                    elif cat == "nsfw":
                        neg_parts.extend([item.strip() for item in self.categories.get("nsfw", []) if item.strip()])
                    else:
                        neg_parts.extend([item.strip() for item in self.categories.get(cat, []) if item.strip()])
                negative_prompt = ", ".join(neg_parts) if neg_parts else negative_config.get("default", "")
            else:
                # そうでなければ default の値を使用
                negative_prompt = negative_config.get("default", "")
            
            # ノードmodsを更新
            if nid not in mods:
                mods[nid] = {"inputs": {}}
            
            # UI形式とAPI形式の両方を更新
            if node.get("_is_ui_format"):
                ui_node = node.get("_ui_node", {})
                w = list(ui_node.get("widgets_values", []))
                if len(w) >= 3:
                    w[0], w[1], w[2] = node_title, positive_prompt, negative_prompt
                    mods[nid]["widgets_values"] = w
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
        
        # 3. nodes_by_id の処理（nodes_by_name より優先して上書き）
        for nid, id_config in self.nodes_by_id.items():
            if nid in current_workflow:
                # 設定ファイルから "inputs" の中身を取り出す
                inputs_cfg = id_config.get("inputs", {})
                
                # 新しい形式 ("assign" が設定されている) 場合の処理
                if "assign" in inputs_cfg:
                    purpose = inputs_cfg.get("purpose", "positive")
                    assign = inputs_cfg.get("assign")
                    default_val = inputs_cfg.get("default", "")
                    
                    text_val = ""
                    
                    if purpose == "positive":
                        if isinstance(assign, str):
                            parts = []
                            # カンマで区切って、一つずつ処理する
                            for cat in [c.strip() for c in assign.split(",")]:
                                if cat == "all":
                                    # all の場合は NSFW と blacklist 以外の全カテゴリを結合
                                    for c, items in self.categories.items():
                                        if c not in ("nsfw", "blacklist"):
                                            parts.extend([item.strip() for item in items if item.strip()])
                                elif cat == "nsfw":
                                    parts.extend([item.strip() for item in self.categories.get("nsfw", []) if item.strip()])
                                else:
                                    # 特定のカテゴリ（head, body など）
                                    parts.extend([item.strip() for item in self.categories.get(cat, []) if item.strip()])
                            
                            # かき集めた単語をカンマで結合する
                            text_val = ", ".join([p for p in parts if p.strip()])
                        else:
                            text_val = ""
                        
                        # もしプロンプトが空っぽになってしまったら default を使う
                        if not text_val.strip():
                            text_val = default_val
                            
                    elif purpose == "negative":
                        if assign is True or str(assign).lower() == "true":
                            # neg 引数があれば使い、なければ default を使う
                            text_val = neg.strip() if neg else default_val
                        elif isinstance(assign, str) and assign:
                            neg_parts = []
                            # Negative側でもカテゴリ指定("all", "head"等)が来た場合の対応
                            for cat in [c.strip() for c in assign.split(",")]:
                                if cat == "all":
                                    for c, items in self.categories.items():
                                        if c not in ("nsfw", "blacklist"): 
                                            neg_parts.extend([i.strip() for i in items if i.strip()])
                                elif cat == "nsfw":
                                    neg_parts.extend([i.strip() for i in self.categories.get("nsfw", []) if i.strip()])
                                else:
                                    neg_parts.extend([i.strip() for i in self.categories.get(cat, []) if i.strip()])
                            text_val = ", ".join(neg_parts) if neg_parts else default_val
                        else:
                            text_val = default_val

                    # ！！！ここです！！！ ユーザー様のご指摘通り、これがないと反映されません
                    if nid not in mods: 
                        mods[nid] = {"inputs": {}}
                    mods[nid]["inputs"]["text"] = text_val
        
        # 4. seed処理と Discord送信
        return self.run(modifications=mods, send_discord=self.output_enabled, workflow=current_workflow)
    
    def _save_active_workflow(self):
        """active_workflow を workflow_settings.json の active_workflow キーに保存。
        ファイル読み込み→該当キーのみ上書き→保存で、workflow_types 等を破壊しない。"""
        try:
            if os.path.exists(self.settings_path):
                with open(self.settings_path, 'r', encoding='utf-8') as f:
                    self.settings = json.load(f)
            else:
                self.settings = {"workflow_types": {}, "active_workflow": self.active_workflow}
            self.settings["active_workflow"] = self.active_workflow
            with open(self.settings_path, 'w', encoding='utf-8') as f:
                json.dump(self.settings, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[_save_active_workflow] Error: {e}")
            pass

    def run(self, modifications=None, send_discord=False, target_num=None, workflow_type='default', workflow=None):
        try:
            # workflow_type が指定されたら active_workflow を更新
            # workflow_type が明示された時だけ load_settings 呼ぶ（draw 内の _save_workflow_after_load パターン使用）
            # ただし run() 自体の workflow_type 更新時は draw() と違い保存済みなので上書き不要
            if workflow_type and workflow_type != self.active_workflow and modifications is None:
                # workflow_types に存在するかチェック（ファイル直接読み）
                settings_path = os.path.join(ComfyCategorizer._BASE_PATH, "workflow_settings.json")
                wf_check = {}
                if os.path.exists(settings_path):
                    with open(settings_path, 'r', encoding='utf-8') as f:
                        wf_check = json.load(f).get("workflow_types", {})
                if workflow_type not in wf_check:
                    raise ValueError(f"Workflow type '{workflow_type}' not found. Available: {list(wf_check.keys())}")
                self.active_workflow = workflow_type
                self._save_workflow_after_load = True
                self.load_settings()
            
            # draw() からの修正依頼がある場合
            if modifications is not None:
                return super().run(modifications=modifications, send_discord=send_discord and self.output_enabled, workflow=workflow)

            # CLI からの直接実行
            if target_num is not None:
                return self._replay_history_item(target_num, workflow_type)
            else:
                return self._fetch_and_process_new(workflow_type)
        except Exception as e:
            return f"Execution Error: {e}"
    
    def _replay_history_item(self, target_num, workflow_type='default'):
        """Replay a specific item from processed_urls.txt history."""
        records = self._get_all_records()
        if not (1 <= target_num <= len(records)):
            return f"Error: 1から{len(records)}までの数値を指定してください。"
        
        page_url, post_id = records[target_num - 1]
        item = self._fetch_item_by_post_id(post_id)
        
        if not item or 'meta' not in item:
            return f"Error: {target_num}件目のデータが取得できませんでした。"
        
        meta = item.get('meta')
        if not isinstance(meta, dict):
            return f"Error: {target_num}件目のデータが取得できませんでした。"
        image_direct_url = item.get('url')
        prompt = meta.get('prompt', '')
        neg_prompt = meta.get('negativePrompt', '')
        
        # Log unclassified words before generation
        self.categorize_prompt(prompt)
        
        # Use legacy draw (no DualPromptEncoder check) for replay
        # Use the categorizer's draw method to generate the image with proper prompt handling
        result = self.draw(prompt=prompt, neg=neg_prompt, workflow_type=workflow_type)
        
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
                if not isinstance(meta, dict) or not meta or 'prompt' not in meta:
                    self._save_processed(page_url, post_id) # 同じURLを二度と踏まないように記録
                    continue
                    
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

E("Dictionaries loaded:", list(cc.dictionaries.keys()))
print("Categories:", cc.categories)

result = cc.categorize_prompt(test_prompt)
print("Result:", result)
```
"""
    
    def execute(self, prompt, workflow=None, workflow_type=None, mods=None):
        """Execute workflow. mods can be passed from draw() to avoid double-building."""
        try:
            # 引数なしの場合は active_workflow を使用
            if workflow_type is None:
                workflow_type = self.active_workflow
            
            # workflow_type が明示的に指定されたら active_workflow を更新
            if workflow_type != self.active_workflow:
                self.active_workflow = workflow_type
                self._save_active_workflow()  # 先に保存（load_settings が上書きするため）
                self.load_settings()  # active_workflow をファイルから再設定
                self._save_active_workflow()
            
            # --- ワークフローファイル解決 ---
            if workflow is None:
                if self.workflowfile:
                    wf_path = os.path.join(ComfyCategorizer._BASE_PATH, "workflows", self.workflowfile)
                    if not os.path.exists(wf_path):
                        raise FileNotFoundError(f"Workflow file not found: {wf_path}")
                    try:
                        with open(wf_path, 'r', encoding='utf-8') as f:
                            workflow = json.load(f)
                        print(f"[ComfyCategorizer] Loaded workflow: {self.workflowfile}")
                    except json.JSONDecodeError as e:
                        raise ValueError(f"Failed to parse workflow JSON ({wf_path}): {e}")
                else:
                    workflow = self.get_latest_history()
                    print(f"[ComfyCategorizer] Loaded workflow: history (no workflowfile configured)")

            if not workflow:
                return {"error": "no_history"}

            # mods が渡されていればそのまま使用（draw からの呼び出し）
            # 渡されていなければここで構築（後方互換性）
            if mods is None:
                self.categorize_prompt(prompt)
                mods = {}
                for node_info in self.get_dual_prompt_encoder_nodes(workflow):
                    nid = node_info["node_id"]
                    node = node_info["node_data"]
                    node_title = node_info["title"]
                    inputs = node.get("inputs", {}) or {}

                    positive_config = self.nodes_by_name.get("positive", {}).get(node_title, {})
                    negative_config = self.nodes_by_name.get("negative", {}).get(node_title, {})

                    positive_prompt = ""
                    assign = positive_config.get("assign")
                    if isinstance(assign, str):
                        parts = []
                        for cat in [c.strip() for c in assign.split(",")]:
                            items = [item.strip() for item in self.categories.get(cat, []) if item.strip()]
                            parts.extend(items)
                        positive_prompt = ", ".join(parts) if parts else positive_config.get("default", "")
                    if not positive_prompt.strip():
                        positive_prompt = positive_config.get("default", prompt)

                    neg_assign = negative_config.get("assign")
                    if neg_assign is True:
                        negative_prompt = ""
                    elif isinstance(neg_assign, str) and neg_assign:
                        neg_parts = []
                        for cat in [c.strip() for c in neg_assign.split(",")]:
                            if cat == "all":
                                for c, items in self.categories.items():
                                    if c not in ("nsfw", "blacklist"): neg_parts.extend([i.strip() for i in items if i.strip()])
                            else:
                                neg_parts.extend([i.strip() for i in self.categories.get(cat, []) if i.strip()])
                        negative_prompt = ", ".join(neg_parts) if neg_parts else negative_config.get("default", "")
                    else:
                        negative_prompt = negative_config.get("default", "")

                    if nid not in mods: mods[nid] = {"inputs": {}}
                    if node.get("_is_ui_format"):
                        ui_node = node.get("_ui_node", {})
                        w = list(ui_node.get("widgets_values", []))
                        if len(w) >= 3: w[0], w[1], w[2] = node_title, positive_prompt, negative_prompt
                        mods[nid]["widgets_values"] = w
                        mods[nid]["inputs"].update({"positive": positive_prompt, "negative": negative_prompt, "name": node_title})
                    else:
                        for key in ["text", "positive", "in_positive"]:
                            if key in inputs: mods[nid]["inputs"][key] = positive_prompt
                        for key in ["negative", "neg_display"]:
                            if key in inputs: mods[nid]["inputs"][key] = negative_prompt
                        mods[nid]["inputs"]["name"] = node_title

                for nid, id_config in self.nodes_by_id.items():
                    if nid in workflow:
                        inputs = workflow[nid].get("inputs", {})
                        for k, v in id_config.get("inputs", {}).items():
                            if k in inputs:
                                if nid not in mods: mods[nid] = {"inputs": {}}
                                if k == "text":
                                    if v == "all":
                                        parts = [i.strip() for c, items in self.categories.items() for i in items if c != "nsfw" and i.strip()]
                                    else: parts = [v]
                                    mods[nid]["inputs"][k] = ", ".join(parts)
                                else:
                                    mods[nid]["inputs"][k] = v

            # mods を apply して実行（workflow を明示的に渡す）
            return self.run(modifications=mods, send_discord=False, workflow=workflow)

        except Exception as e:
            return {"error": str(e)}

    def debug_print_categorization(self, original_prompt, original_neg=""):
        """仕分け結果を詳細に標準出力するデバッグ用メソッド"""
        print("\n" + "="*50)
        print(" [DEBUG] Prompt Categorization Details")
        print("="*50)
        
        # 1. Civitaiから取得した生のプロンプトを表示
        print(f"\n[Original Positive Prompt]:\n{original_prompt}")
        print(f"\n[Original Negative Prompt]:\n{original_neg}")
        print("-" * 30)

        # 2. 仕分け実行（戻り値を保存して2回呼出を防止）
        cat_result = self.categorize_prompt(original_prompt)

        # 3. 各辞書（カテゴリ）ごとの割り当て状況を表示
        print("\n[Dictionary Assignment]:")
        for cat, words in self.categories.items():
            if cat == "all": continue # allは後で表示
            if words:
                print(f"  - {cat:10}: {', '.join(words)}")
            else:
                print(f"  - {cat:10}: (None)")

        # 4. 'all' カテゴリの合算結果（NSFW除外済みの全ワード）
        print(f"\n['all' Category Combined]:\n{', '.join(self.categories.get('all', []))}")

        # 5. 未分類単語の確認
        # self.categorize_prompt の戻り値から未分類を取得
        unclassified = cat_result.get("unclassified", [])
        if unclassified:
            print(f"\n[Unclassified Words]:\n{', '.join(unclassified)}")

        print("="*50 + "\n")
# --- CLI entry point ---

def list_workflows(cc):
    """--list: 一覧表示（高度化版）"""
    print("\n=== 登録ワークフロー一覧 ===")
    wf_types = cc.settings.get("workflow_types", {})
    if not wf_types:
        print("設定が見つかりません")
        return
    
    keys = list(wf_types.keys())
    for i, name in enumerate(keys, 1):
        config = wf_types[name]
        active = " (active)" if name == cc.active_workflow else ""
        print(f"\n{i}. {name}{active}")
        print(f"   workflowfile: {config.get('workflowfile', 'なし')}")
        print(f"   output_enabled: {config.get('output_enabled', True)}")
        
        # nodes_by_name 表示
        nodes_by_name = config.get("nodes_by_name", {})
        pos_nodes = nodes_by_name.get("positive", {})
        neg_nodes = nodes_by_name.get("negative", {})
        
        print("   --- nodes_by_name ---")
        if pos_nodes:
            print("   positive:")
            for node_name, node_config in pos_nodes.items():
                print(f"     - {node_name}: assign='{node_config.get('assign', '')}', default='{node_config.get('default', '')}'")
        if neg_nodes:
            print("   negative:")
            for node_name, node_config in neg_nodes.items():
                print(f"     - {node_name}: assign={node_config.get('assign', '')}, default='{node_config.get('default', '')}'")
        
        # nodes_by_id 表示
        nodes_by_id = config.get("nodes_by_id", {})
        if nodes_by_id:
            print("   --- nodes_by_id ---")
            for nid, id_config in nodes_by_id.items():
                purpose = id_config.get("purpose", "unknown")
                assign = id_config.get("assign", "")
                default = id_config.get("default", "")
                print(f"     - ID {nid}: purpose={purpose}, assign={assign}, default='{default}'")
    print()

def add_workflow(cc):
    """--add: 新規追加（実体ベース版）"""
    print("\n=== 新規ワークフロー追加（実体ベースウィザード） ===")
    
    # 設定名
    name = input("設定名: ").strip()
    if not name:
        print("キャンセルしました")
        return
    if name in cc.settings.get("workflow_types", {}):
        print(f"エラー: {name} は既に存在します")
        return
    
    # ワークフローファイル（必須）
    wf_file = input("ワークフローファイル名 (workflows/内): ").strip()
    if not wf_file:
        print("ワークフローファイルが必要です")
        return
    
    # ワークフロー解析（強制）
    wf_path = os.path.join(os.path.dirname(cc.settings_path), "workflows", wf_file)
    workflow = None
    if os.path.exists(wf_path):
        try:
            with open(wf_path, 'r', encoding='utf-8') as f:
                workflow = json.load(f)
            print(f"\n✅ {wf_file} を読み込みました")
        except Exception as e:
            print(f"⚠️ {wf_file} の読み込みに失敗しました: {e}")
    else:
        print(f"⚠️ {wf_file} が見つかりません")
        return
    
    # 出力設定 - 実行履歴保存の質問
    output_enabled = input("実行履歴を保存しますか？ (y/n) [y]: ").strip().lower() != 'n'
    
    # Discord送信設定
    discord_send = input("Discordに画像を送信しますか？ (y/n) [y]: ").strip().lower() != 'n'
    # discord_send が False でも output_enabled が True なら履歴は保存される
    
    # 抽出（ID順ソート）
    nodes_by_name = {"positive": {}, "negative": {}}
    nodes_by_id = {}
    target_nodes = []
    
    if workflow:
        for nid, node in workflow.items():
            class_type = node.get("class_type", "")
            if class_type in ["DualPromptEncoder", "CLIPTextEncode"]:
                inputs = node.get("inputs", {})
                # 初期値を取得
                init_values = {}
                if class_type == "DualPromptEncoder":
                    init_values = {
                        "name": inputs.get("name", ""),
                        "positive": inputs.get("positive", ""),
                        "negative": inputs.get("negative", "")
                    }
                elif class_type == "CLIPTextEncode":
                    init_values = {
                        "text": inputs.get("text", "")
                    }
                target_nodes.append({
                    "id": str(nid),
                    "class_type": class_type,
                    "init_values": init_values
                })
        
        # ID順でソート
        target_nodes.sort(key=lambda x: int(x["id"]) if x["id"].isdigit() else 0)
        
        if not target_nodes:
            print("DualPromptEncoder と CLIPTextEncode が見つかりませんでした")
        else:
            for node_info in target_nodes:
                nid = node_info["id"]
                class_type = node_info["class_type"]
                init = node_info["init_values"]
                
                # ステップ1：ノードの提示と編集確認
                print(f"\n[{nid}]: class_type : {class_type}")
                edit_q = input("Edit (y/n) [n]: ").strip().lower()
                
                if edit_q != 'y':
                    continue
                
                if class_type == "DualPromptEncoder":
                    # --- DualPromptEncoder 設定 ---
                    print("  --- DualPromptEncoder 詳細設定 ---")
                    
                    # name（論理名）- 表示のみ、編集不可
                    current_name = init.get("name", "")
                    print(f"  name: {current_name} (表示のみ、編集不可)")
                    
                    # positive categories - 初回は空欄とする（カテゴリ名入力を容易にする）
                    pos_assign = input("  positive categories []: ").strip()
                    
                    # positive default - ワークフロー内の生プロンプトを初期値として提示
                    current_positive = init.get("positive", "")
                    pos_default = input(f"  positive default [{current_positive}]: ").strip()
                    if not pos_default:
                        pos_default = current_positive
                    
                    # negative 設定
                    current_neg = init.get("negative", "")
                    neg_assign = input(f"  negative (true/all/カテゴリ) [{current_neg}]: ").strip()
                    if not neg_assign:
                        neg_assign = current_neg
                    
                    # negative default
                    neg_default = input("  negative default [low quality, worst quality]: ").strip()
                    if not neg_default:
                        neg_default = "low quality, worst quality"
                    
                    # nodes_by_name に保存（positive/negative 分離）
                    nodes_by_name["positive"][current_name] = {
                        "assign": pos_assign,
                        "default": pos_default
                    }
                    nodes_by_name["negative"][current_name] = {
                        "assign": neg_assign,
                        "default": neg_default
                    }
                    
                    print(f"  ✅ {current_name} を設定しました")
                    
                elif class_type == "CLIPTextEncode":
                    # --- CLIPTextEncode 設定 ---
                    print("  --- CLIPTextEncode 詳細設定 ---")
                    
                    # ステップ2：用途確認
                    print("  このノードの用途を選択:")
                    print("    1: Positive用")
                    print("    2: Negative用")
                    purpose = input("  選択 [1]: ").strip()
                    is_negative = purpose == "2"
                    
                    # ステップ3：詳細設定
                    if is_negative:
                        # Negative用
                        use_neg = input("  neg引数を使用 (y/n) [n]: ").strip().lower() == 'y'
                        default_val = input("  default [low quality, worst quality]: ").strip()
                        if not default_val:
                            default_val = "low quality, worst quality"
                        
                        # --- 修正部分: "inputs" で囲んで保存する ---
                        nodes_by_id[nid] = {
                            "inputs": {
                                "purpose": "negative",
                                "assign": use_neg,
                                "default": default_val
                            }
                        }
                    else:
                        # Positive用
                        current_text = init.get("text", "")
                        categories = input(f"  categories [{current_text}]: ").strip()
                        if not categories:
                            categories = current_text
                        default_val = input("  default []: ").strip()
                        
                        # --- 修正部分: "inputs" で囲んで保存する ---
                        nodes_by_id[nid] = {
                            "inputs": {
                                "purpose": "positive",
                                "assign": categories,
                                "default": default_val
                            }
                        }
                    
                    print(f"  ✅ ノードID {nid} を設定しました")
    
    # 保存
    if "workflow_types" not in cc.settings:
        cc.settings["workflow_types"] = {}
    cc.settings["workflow_types"][name] = {
        "workflowfile": wf_file,
        "output_enabled": output_enabled,
        "nodes_by_name": nodes_by_name,
        "nodes_by_id": nodes_by_id
    }
    
    # 新規作成したワークフローを active_workflow として保存
    cc.active_workflow = name
    cc.settings["active_workflow"] = name  # ← 修正部分: cc._save_active_workflow() の代わりに直接代入！
    
    with open(cc.settings_path, 'w', encoding='utf-8') as f:
        json.dump(cc.settings, f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ {name} を追加しました (active_workflow = {name})")
    print(f"   nodes_by_name positive: {list(nodes_by_name['positive'].keys())}")
    print(f"   nodes_by_name negative: {list(nodes_by_name['negative'].keys())}")
    print(f"   nodes_by_id: {list(nodes_by_id.keys())}")

def edit_workflow(cc):
    """--edit: 既存編集（実体ベース版）"""
    print("\n=== ワークフロー編集（実体ベース） ===")
    wf_types = cc.settings.get("workflow_types", {})
    keys = list(wf_types.keys())
    
    if not keys:
        print("編集可能な設定がありません")
        return
    
    # 選択
    print("編集したい設定を選択してください:")
    for i, name in enumerate(keys, 1):
        print(f"{i}. {name}")
    
    try:
        choice = int(input("番号: ").strip())
        name = keys[choice - 1]
    except:
        print("キャンセルしました")
        return
    
    config = wf_types[name]
    
    # workflowfile を取得してワークフローを解析
    wf_file = config.get("workflowfile", "")
    wf_path = os.path.join(os.path.dirname(cc.settings_path), "workflows", wf_file)
    workflow = None
    
    print(f"\n--- {name} の編集 ---")
    print(f"workflowfile: {wf_file}")
    
    # ワークフロー解析
    if os.path.exists(wf_path):
        try:
            with open(wf_path, 'r', encoding='utf-8') as f:
                workflow = json.load(f)
            print(f"✅ {wf_file} を読み込みました")
        except:
            print(f"⚠️ {wf_file} の読み込みに失敗しました")
    else:
        print(f"⚠️ {wf_file} が見つかりません")
    
    # 出力設定 - 実行履歴保存の質問
    current_out = config.get("output_enabled", True)
    new_out = input(f"実行履歴を保存しますか？ (y/n) [{current_out}]: ").strip().lower()
    if new_out == 'y':
        config["output_enabled"] = True
    elif new_out == 'n':
        config["output_enabled"] = False
    
    # Discord送信設定（output_enabled とは別）
    current_discord = config.get("discord_enabled", True)
    new_discord = input(f"Discordに画像を送信しますか？ (y/n) [{current_discord}]: ").strip().lower()
    if new_discord == 'y':
        config["discord_enabled"] = True
    elif new_discord == 'n':
        config["discord_enabled"] = False
    
    # 既存のnodes_by_name, nodes_by_id を取得
    nodes_by_name = config.get("nodes_by_name", {"positive": {}, "negative": {}})
    nodes_by_id = config.get("nodes_by_id", {})
    
    # ワークフロー内のノードを抽出（ID順）
    target_nodes = []
    if workflow:
        for nid, node in workflow.items():
            class_type = node.get("class_type", "")
            if class_type in ["DualPromptEncoder", "CLIPTextEncode"]:
                inputs = node.get("inputs", {})
                init_values = {}
                if class_type == "DualPromptEncoder":
                    init_values = {
                        "name": inputs.get("name", ""),
                        "positive": inputs.get("positive", ""),
                        "negative": inputs.get("negative", "")
                    }
                elif class_type == "CLIPTextEncode":
                    init_values = {
                        "text": inputs.get("text", "")
                    }
                target_nodes.append({
                    "id": str(nid),
                    "class_type": class_type,
                    "init_values": init_values
                })
        
        target_nodes.sort(key=lambda x: int(x["id"]) if x["id"].isdigit() else 0)
    
    # 各ノードに対して編集
    for node_info in target_nodes:
        nid = node_info["id"]
        class_type = node_info["class_type"]
        init = node_info["init_values"]
        
        # ステップ1：ノードの提示と編集確認
        print(f"\n[{nid}]: class_type : {class_type}")
        
        # 既に設定があるか表示
        existing_config = None
        if class_type == "DualPromptEncoder":
            node_name = init.get("name", "")
            for section in ["positive", "negative"]:
                if node_name in nodes_by_name.get(section, {}):
                    existing_config = nodes_by_name[section][node_name]
                    print(f"  現在の設定: assign='{existing_config.get('assign', '')}', default='{existing_config.get('default', '')}'")
                    break
        elif class_type == "CLIPTextEncode":
            # --- 修正部分：現在の設定を "inputs" から取得するように変更 ---
            if nid in nodes_by_id:
                existing_config = nodes_by_id[nid].get("inputs", {})
                print(f"  現在の設定: purpose={existing_config.get('purpose', '')}, assign={existing_config.get('assign', '')}, default='{existing_config.get('default', '')}'")
        
        edit_q = input("Edit (y/n) [n]: ").strip().lower()
        
        if edit_q != 'y':
            continue
        
        if class_type == "DualPromptEncoder":
            # --- DualPromptEncoder 編集 ---
            print("  --- DualPromptEncoder 詳細設定 ---")
            
            current_name = init.get("name", "")
            # name - 表示のみ、編集不可（drawがノード特定不能再発防止）
            print(f"  name: {current_name} (表示のみ、編集不可)")
            
            # positive設定 - 初期値表示なし（カテゴリ入力を容易にする）
            if existing_config:
                current_pos_assign = existing_config.get("assign", "")
                current_pos_default = existing_config.get("default", "") or init.get("positive", "")
            else:
                current_pos_assign = ""
                current_pos_default = init.get("positive", "")
            
            pos_assign = input(f"  positive categories [{current_pos_assign}]: ").strip()
            if not pos_assign and existing_config:
                pos_assign = current_pos_assign
            pos_default = input(f"  positive default [{current_pos_default}]: ").strip()
            if not pos_default:
                pos_default = current_pos_default
            
            # negative設定
            if existing_config:
                current_neg_assign = existing_config.get("assign", "") or init.get("negative", "")
            else:
                current_neg_assign = init.get("negative", "")
            
            neg_assign = input(f"  negative (true/all/カテゴリ) [{current_neg_assign}]: ").strip()
            if not neg_assign and existing_config:
                neg_assign = current_neg_assign
            
            neg_default = input("  negative default [low quality, worst quality]: ").strip()
            if not neg_default:
                neg_default = "low quality, worst quality"
            
            # 保存 - current_name をそのまま使用
            nodes_by_name["positive"][current_name] = {
                "assign": pos_assign,
                "default": pos_default
            }
            nodes_by_name["negative"][current_name] = {
                "assign": neg_assign,
                "default": neg_default
            }
            
            print(f"  ✅ {current_name} を更新しました")
            
        elif class_type == "CLIPTextEncode":
            # --- CLIPTextEncode 編集 ---
            print("  --- CLIPTextEncode 詳細設定 ---")
            
            # 1. 以前の設定を "inputs" の中から読み取るように変更
            current_config = nodes_by_id.get(nid, {}).get("inputs", {})
            current_purpose = current_config.get("purpose", "positive")
            
            print("  このノードの用途を選択:")
            print("    1: Positive用")
            print("    2: Negative用")
            purpose = input(f"  選択 [{'2' if current_purpose == 'negative' else '1'}]: ").strip()
            if not purpose:
                purpose = "2" if current_purpose == "negative" else "1"
            is_negative = purpose == "2"
            
            # 詳細設定
            if is_negative:
                # 前回の値をデフォルト表示にする
                current_assign = current_config.get("assign", False)
                def_y_n = "y" if current_assign in [True, "true", "True"] else "n"
                
                use_neg = input(f"  neg引数を使用 (y/n) [{def_y_n}]: ").strip().lower()
                if not use_neg:
                    use_neg = def_y_n
                use_neg_bool = use_neg == 'y'
                
                current_default = current_config.get("default", "low quality, worst quality")
                default_val = input(f"  default [{current_default}]: ").strip()
                if not default_val:
                    default_val = current_default
                
                # --- 修正部分：安全に中身を上書きする ---
                if nid not in nodes_by_id:
                    nodes_by_id[nid] = {"inputs": {}}
                elif "inputs" not in nodes_by_id[nid]:
                    nodes_by_id[nid]["inputs"] = {}
                
                nodes_by_id[nid]["inputs"]["purpose"] = "negative"
                nodes_by_id[nid]["inputs"]["assign"] = use_neg_bool
                nodes_by_id[nid]["inputs"]["default"] = default_val
            else:
                # Positive用の前回設定値を読み込む
                current_assign = current_config.get("assign", init.get("text", ""))
                categories = input(f"  categories [{current_assign}]: ").strip()
                if not categories:
                    categories = current_assign
                    
                current_default = current_config.get("default", "")
                default_val = input(f"  default [{current_default}]: ").strip()
                if not default_val:
                    default_val = current_default
                
                # 2. 保存する時に "inputs" で囲む
                nodes_by_id[nid] = {
                    "inputs": {
                        "purpose": "positive",
                        "assign": categories,
                        "default": default_val
                    }
                }
            
            print(f"  ✅ ノードID {nid} を更新しました")
    
    # 修正部分：新しく書き換えた nodes_by_name と nodes_by_id を config に確実に上書きする
    config["nodes_by_name"] = nodes_by_name
    config["nodes_by_id"] = nodes_by_id
    
    # 保存
    cc.settings["workflow_types"][name] = config
    
    # 編集したワークフローを active_workflow として保存
    cc.active_workflow = name
    cc.settings["active_workflow"] = name
    
    with open(cc.settings_path, 'w', encoding='utf-8') as f:
        json.dump(cc.settings, f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ {name} を更新しました (active_workflow = {name})")
    print(f"   nodes_by_name positive: {list(nodes_by_name.get('positive', {}).keys())}")
    print(f"   nodes_by_name negative: {list(nodes_by_name.get('negative', {}).keys())}")
    print(f"   nodes_by_id: {list(nodes_by_id.keys())}")

def delete_workflow(cc):
    """--delete: 削除"""
    print("\n=== ワークフロー削除 ===")
    wf_types = cc.settings.get("workflow_types", {})
    keys = list(wf_types.keys())
    
    if not keys:
        print("削除可能な設定がありません")
        return
    
    # 選択
    print("削除したい設定を選択してください:")
    for i, name in enumerate(keys, 1):
        print(f"{i}. {name}")
    
    try:
        choice = int(input("番号: ").strip())
        name = keys[choice - 1]
    except:
        print("キャンセルしました")
        return
    
    # 確認
    confirm = input(f"本当に {name} を削除しますか？ (y/n): ").strip().lower()
    if confirm != 'y':
        print("キャンセルしました")
        return
    
    # 削除
    del cc.settings["workflow_types"][name]
    with open(cc.settings_path, 'w', encoding='utf-8') as f:
        json.dump(cc.settings, f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ {name} を削除しました")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="ComfyCategorizer CLI")
    parser.add_argument("--list", action="store_true", help="設定一覧を表示")
    parser.add_argument("--add", action="store_true", help="新規設定を追加")
    parser.add_argument("--edit", action="store_true", help="既存設定を編集")
    parser.add_argument("--delete", action="store_true", help="設定を削除")
    parser.add_argument("args", nargs="*", help="従来形式: target_num,workflow_type")
    
    args = parser.parse_args()
    cc = ComfyCategorizer()
    
    # --- 1. 変数の初期化 (ウィザードモードでも参照できるように外側で定義) ---
    target_num = None
    workflow_type = cc.active_workflow
    is_wizard = False

    # --- 2. モード判定 ---
    if args.list:
        list_workflows(cc)
        is_wizard = True
    elif args.add:
        add_workflow(cc)
        is_wizard = True
    elif args.edit:
        edit_workflow(cc)
        is_wizard = True
    elif args.delete:
        delete_workflow(cc)
        is_wizard = True
    else:
        # 従来モード: 引数を解析して target_num や workflow_type を決定
        for arg in args.args:
            if arg.isdigit():
                target_num = int(arg)
            elif ',' in arg:
                parts = arg.split(',')
                if parts[0].isdigit():
                    target_num = int(parts[0])
                if len(parts) > 1:
                    workflow_type = parts[1].strip()
            else:
                workflow_type = arg

    # --- 3. 実行 (ウィザードモード単体で動かした場合は実行をスキップ) ---
    if not is_wizard:
        # 手前でのフライング保存・ロードは削除し、cc.run内の存在チェックへ一本化
        result = cc.run(target_num=target_num, workflow_type=workflow_type)
        print("Result:", result)
    else:
        print("\nWizard finished.")