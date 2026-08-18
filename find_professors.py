import os
import time
import requests
import pandas as pd

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

FILE_NAME = "List of emails.xlsx - Sheet1.csv" if os.path.exists("List of emails.xlsx - Sheet1.csv") else "List of emails.xlsx"

# ==============================================================================
# FULL COMPREHENSIVE RESEARCH TAXONOMY
# ==============================================================================
KEYWORD_GROUPS = [
    # Group 1: Core UWB, Localization & Channel Physics (Tier 1)
    [
        "ultra-wideband", "UWB localization", "UWB positioning",
        "indoor positioning", "indoor localization", "wireless localization",
        "radio-based localization", "fingerprinting localization",
        "channel impulse response", "channel state information", "CSI sensing",
        "time of flight", "TDoA", "NLOS localization", "multipath SLAM"
    ],
    # Group 2: Wireless Sensing, Radar & Sensor Fusion (Tier 2)
    [
        "wireless sensing", "RF sensing", "radio sensing", "radar sensing",
        "millimeter wave sensing", "mmWave localization", "sensor fusion",
        "multimodal sensing", "Bayesian tracking", "pedestrian dead reckoning",
        "integrated sensing and communications", "ISAC", "6G localization"
    ],
    # Group 3: Embedded AI, Edge Computing, Hardware & Robotics (Tier 3)
    [
        "edge AI", "tinyML", "embedded machine learning", "FPGA hardware accelerator",
        "low-power embedded systems", "deep learning localization",
        "computer vision autonomous systems", "CARLA simulation autonomous"
    ]
]

def send_telegram_message(text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[!] Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID!")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }
    try:
        res = requests.post(url, json=payload, timeout=20)
        if res.status_code != 200:
            print(f"[!] Telegram send error: {res.text}")
    except Exception as e:
        print(f"[!] Telegram connection error: {e}")

def send_telegram_document(file_path, caption=""):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendDocument"
    try:
        with open(file_path, "rb") as doc:
            requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "caption": caption}, files={"document": doc}, timeout=35)
    except Exception as e:
        print(f"[!] Telegram doc send error: {e}")

def search_faculty_at_institution(uni_name):
    """Searches OpenAlex sequentially across all keyword groups for matching faculty."""
    discovered = []
    headers = {"User-Agent": "mailto:phd_lead_bot@academic.org"}
    
    # 1. Resolve institution ID
    try:
        inst_url = f"https://api.openalex.org/institutions?search={requests.utils.quote(str(uni_name))}"
        res = requests.get(inst_url, headers=headers, timeout=15).json()
        if not res.get("results"):
            return discovered
        inst_id = res["results"][0]["id"]
    except Exception as e:
        print(f"Error resolving university ID for {uni_name}: {e}")
        return discovered

    # 2. Iterate through keyword groups until matches are found
    for group_idx, group in enumerate(KEYWORD_GROUPS, start=1):
        # Format query: "term1" OR "term2" OR ...
        query_str = " OR ".join([f'"{k}"' for k in group[:6]])
        works_url = (
            f"https://api.openalex.org/works?"
            f"filter=authorships.institutions.id:{inst_id},from_publication_date:2023-01-01"
            f"&search={requests.utils.quote(query_str)}"
            f"&per-page=3"
        )
        try:
            w_res = requests.get(works_url, headers=headers, timeout=15).json()
            works = w_res.get("results", [])
            if works:
                for work in works:
                    title = work.get("title", "N/A")
                    pub_year = work.get("publication_year", "")
                    authorships = work.get("authorships", [])
                    
                    # Target senior lab author (last author) or first author
                    selected_author = authorships[-1] if len(authorships) > 1 else (authorships[0] if authorships else None)
                    if selected_author:
                        author_info = selected_author.get("author", {})
                        discovered.append({
                            "professor": author_info.get("display_name", "Unknown PI"),
                            "university": uni_name,
                            "paper": title,
                            "year": pub_year,
                            "tier": f"Tier {group_idx}",
                            "profile_url": author_info.get("id", "")
                        })
                break  # Stop at first matching group (Tier 1 > Tier 2 > Tier 3)
        except Exception as e:
            print(f"Error querying works for {uni_name} in group {group_idx}: {e}")
            
    return discovered

def main():
    print(f"Loading file: {FILE_NAME}")
    df = pd.read_csv(FILE_NAME) if FILE_NAME.endswith(".csv") else pd.read_excel(FILE_NAME)

    if "Checked?" not in df.columns:
        df["Checked?"] = "NO"

    mask = (
        (df["University"].notna()) & 
        (df["University"].astype(str).str.strip() != "") & 
        (df["Checked?"] != "YES")
    )
    pending_rows = df[mask]

    if pending_rows.empty:
        send_telegram_message("🎉 All universities in your list have already been processed!")
        return

    batch = pending_rows.head(5)
    universities = batch["University"].tolist()

    send_telegram_message(
        f"🔍 *Scanning 5 Target Universities Across All Research Tiers:*\n" + 
        "\n".join([f"• {u}" for u in universities])
    )

    all_matches = []
    for idx, row in batch.iterrows():
        uni = str(row["University"]).strip()
        profs = search_faculty_at_institution(uni)
        df.at[idx, "Checked?"] = "YES"
        
        if profs:
            all_matches.extend(profs)
            if pd.isna(df.at[idx, "Professor"]) or str(df.at[idx, "Professor"]).strip() == "":
                df.at[idx, "Professor"] = profs[0]["professor"]
                df.at[idx, "Subject"] = profs[0]["paper"]
                
        time.sleep(1)

    # Save progress
    if FILE_NAME.endswith(".csv"):
        df.to_csv(FILE_NAME, index=False)
    else:
        df.to_excel(FILE_NAME, index=False)

    # Send report
    if all_matches:
        msg = f"🎯 *Discovered {len(all_matches)} Professors & Lab Leads:*\n\n"
        for item in all_matches[:8]:
            msg += (
                f"🏛 *{item['university']}* `[{item['tier']}]`\n"
                f"👤 *Prof/PI:* {item['professor']}\n"
                f"📄 *Paper ({item['year']}):* _{item['paper'][:80]}..._\n"
                f"🔗 [OpenAlex Profile]({item['profile_url']})\n\n"
            )
        send_telegram_message(msg)
    else:
        send_telegram_message("⚠️ Scanned 5 universities, but found no recent publications matching any of the three research tiers.")

    send_telegram_document(FILE_NAME, caption="💾 Updated tracking sheet.")

if __name__ == "__main__":
    main()
