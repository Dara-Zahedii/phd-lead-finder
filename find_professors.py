import os
import time
import requests
import pandas as pd

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

FILE_NAME = "List of emails.xlsx" if os.path.exists("List of emails.xlsx") else "List of emails.xlsx - Sheet1.csv"

RESEARCH_KEYWORDS = [
    "ultra-wideband", "UWB localization", "indoor positioning",
    "channel impulse response", "CSI sensing", "fingerprinting localization",
    "RF sensing", "edge AI", "sensor fusion"
]

def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }
    requests.post(url, json=payload, timeout=15)

def send_telegram_document(file_path, caption=""):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendDocument"
    with open(file_path, "rb") as doc:
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "caption": caption}, files={"document": doc}, timeout=30)

def search_faculty_at_university(uni_name):
    discovered = []
    headers = {"User-Agent": "mailto:academic_finder@example.com"}
    
    try:
        inst_url = f"https://api.openalex.org/institutions?search={requests.utils.quote(str(uni_name))}"
        inst_res = requests.get(inst_url, headers=headers, timeout=10).json()
        if not inst_res.get("results"):
            return discovered
        inst_id = inst_res["results"][0]["id"]
    except Exception:
        return discovered

    query_terms = " OR ".join([f'"{k}"' for k in RESEARCH_KEYWORDS[:4]])
    works_url = (
        f"https://api.openalex.org/works?"
        f"filter=authorships.institutions.id:{inst_id},from_publication_date:2023-01-01"
        f"&search={requests.utils.quote(query_terms)}"
        f"&per-page=3"
    )
    
    try:
        w_res = requests.get(works_url, headers=headers, timeout=10).json()
        for work in w_res.get("results", []):
            title = work.get("title", "N/A")
            pub_year = work.get("publication_year", "")
            
            for authorship in work.get("authorships", []):
                author = authorship.get("author", {})
                author_name = author.get("display_name", "")
                author_id = author.get("id", "")
                
                discovered.append({
                    "professor": author_name,
                    "university": uni_name,
                    "paper": title,
                    "year": pub_year,
                    "link": author_id
                })
                break
    except Exception as e:
        print(f"Error querying {uni_name}: {e}")
        
    return discovered

def main():
    if FILE_NAME.endswith(".csv"):
        df = pd.read_csv(FILE_NAME)
    else:
        df = pd.read_excel(FILE_NAME)

    if "Checked?" not in df.columns:
        df["Checked?"] = "NO"

    mask = (df["University"].notna()) & (df["Checked?"] != "YES") & (df["University"].astype(str).str.strip() != "")
    pending_rows = df[mask]

    if pending_rows.empty:
        send_telegram_message("🎉 All universities in your list have already been checked!")
        return

    batch = pending_rows.head(5)
    universities = batch["University"].tolist()
    
    send_telegram_message(
        f"🔍 *Daily Batch (5 Universities):*\n" + "\n".join([f"• {u}" for u in universities])
    )

    all_matches = []
    for idx, row in batch.iterrows():
        uni = row["University"]
        profs = search_faculty_at_university(uni)
        df.at[idx, "Checked?"] = "YES"
        if profs:
            all_matches.extend(profs)
        time.sleep(1)

    if FILE_NAME.endswith(".csv"):
        df.to_csv(FILE_NAME, index=False)
    else:
        df.to_excel(FILE_NAME, index=False)

    if all_matches:
        msg = f"✨ *Discovered {len(all_matches)} Professors / Active Labs:*\n\n"
        for item in all_matches:
            msg += (
                f"🏛 *{item['university']}*\n"
                f"👤 *Prof/Author:* {item['professor']}\n"
                f"📄 *Paper ({item['year']}):* _{item['paper'][:80]}..._\n"
                f"🔗 [Profile]({item['link']})\n\n"
            )
        send_telegram_message(msg)
    else:
        send_telegram_message("⚠️ No high-match recent papers found for these 5 universities with the current keywords.")

    send_telegram_document(FILE_NAME, caption="💾 Updated tracking file (Daily Progress).")

if __name__ == "__main__":
    main()