import os
import re
import time
import requests
import pandas as pd

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# Detect working file
CSV_FILE = "List of emails.xlsx - Sheet1.csv"
XLSX_FILE = "List of emails.xlsx"

FILE_TO_LOAD = XLSX_FILE if os.path.exists(XLSX_FILE) else CSV_FILE

SEARCH_GROUPS = [
    ["ultra-wideband", "indoor localization", "indoor positioning", "channel impulse response", "CSI sensing", "TDoA"],
    ["wireless localization", "RF sensing", "sensor fusion", "ISAC", "6G localization", "pedestrian dead reckoning"],
    ["edge AI", "tinyML", "FPGA hardware accelerator", "embedded machine learning", "autonomous systems localization"]
]

def send_telegram_html(text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[!] Missing Telegram credentials.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    requests.post(url, json=payload, timeout=20)

def clean_university_name(name):
    """Normalizes university names so OpenAlex finds them reliably."""
    name = str(name).strip()
    # If combined like "ETH Zürich and Bologna" or "IMEC / KU Leuven", take first main part
    if " and " in name:
        name = name.split(" and ")[0]
    if " / " in name:
        name = name.split(" / ")[-1]  # e.g., 'IMEC / KU Leuven' -> 'KU Leuven'
    name = re.sub(r'\(.*?\)', '', name)  # Remove (QS 519), (UCI), etc.
    name = re.sub(r'[",]', '', name)
    return name.strip()

def search_faculty(raw_uni_name):
    clean_name = clean_university_name(raw_uni_name)
    print(f"--> Searching OpenAlex for: {clean_name} (from: {raw_uni_name})")
    discovered = []
    headers = {"User-Agent": "mailto:phd_bot@academic.org"}

    try:
        inst_url = f"https://api.openalex.org/institutions?search={requests.utils.quote(clean_name)}"
        res = requests.get(inst_url, headers=headers, timeout=15).json()
        if not res.get("results"):
            print(f"    [!] Institution not resolved for: {clean_name}")
            return discovered
        inst_id = res["results"][0]["id"]
    except Exception as e:
        print(f"    [!] Error looking up institution: {e}")
        return discovered

    for group in SEARCH_GROUPS:
        query_str = " OR ".join([f'"{k}"' for k in group])
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
                    
                    # Grab senior PI (last author) or first author
                    chosen = authorships[-1] if len(authorships) > 1 else (authorships[0] if authorships else None)
                    if chosen:
                        author_info = chosen.get("author", {})
                        discovered.append({
                            "professor": author_info.get("display_name", "Lab PI"),
                            "university": raw_uni_name,
                            "paper": title,
                            "year": pub_year,
                            "profile_url": author_info.get("id", "")
                        })
                break
        except Exception as e:
            print(f"    [!] Error querying works: {e}")

    return discovered

def main():
    print(f"Reading file: {FILE_TO_LOAD}")
    if FILE_TO_LOAD.endswith(".csv"):
        df = pd.read_csv(FILE_TO_LOAD)
    else:
        df = pd.read_excel(FILE_TO_LOAD)

    if "Checked?" not in df.columns:
        df["Checked?"] = "NO"

    # Prioritize rows where University exists, Professor is EMPTY, and not checked yet
    mask = (
        (df["University"].notna()) & 
        (df["University"].astype(str).str.strip() != "") & 
        (df["University"].astype(str).str.lower() != "nan") &
        (df["Checked?"].astype(str).str.upper() != "YES")
    )
    pending_rows = df[mask]

    if pending_rows.empty:
        print("[✓] All universities checked.")
        send_telegram_html("🎉 <b>All universities in your Excel have been processed!</b>")
        return

    # Process next batch of 5
    batch = pending_rows.head(5)
    universities = batch["University"].tolist()
    print(f"Processing Batch of 5: {universities}")

    all_matches = []
    for idx, row in batch.iterrows():
        uni = str(row["University"]).strip()
        profs = search_faculty(uni)
        df.at[idx, "Checked?"] = "YES"

        if profs:
            all_matches.extend(profs)
            # Write discovered PI and paper directly into the row
            df.at[idx, "Professor"] = profs[0]["professor"]
            df.at[idx, "Subject"] = f"{profs[0]['paper']} ({profs[0]['year']})"
            df.at[idx, "Note"] = profs[0]["profile_url"]
        time.sleep(1)

    # Save to BOTH CSV and XLSX to ensure sync
    try:
        df.to_excel(XLSX_FILE, index=False)
        print(f"[✓] Saved updated {XLSX_FILE}")
    except Exception:
        pass

    try:
        df.to_csv(CSV_FILE, index=False)
        print(f"[✓] Saved updated {CSV_FILE}")
    except Exception:
        pass

    # Send report to Telegram
    if all_matches:
        msg = f"🎯 <b>Discovered {len(all_matches)} New Professors (5 Universities):</b>\n\n"
        for item in all_matches:
            msg += (
                f"🏛 <b>{item['university']}</b>\n"
                f"👤 <b>PI:</b> {item['professor']}\n"
                f"📄 <b>Recent Work ({item['year']}):</b> <i>{item['paper'][:85]}...</i>\n"
                f"🔗 <a href='{item['profile_url']}'>OpenAlex Author Profile</a>\n\n"
            )
        send_telegram_html(msg)
    else:
        send_telegram_html(
            f"🔍 <b>Checked 5 Universities:</b>\n" + 
            "\n".join([f"• {u}" for u in universities]) + 
            "\n\n<i>No direct open publications found in this cycle.</i>"
        )

if __name__ == "__main__":
    main()
