import csv
import re
import os
import sys
import html
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinterdnd2 import DND_FILES, TkinterDnD

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def find_databases():
    primary_db = ""; ai_db = ""
    try:
        if getattr(sys, 'frozen', False):
            current_dir = os.path.dirname(sys.executable)
        else:
            current_dir = os.path.dirname(os.path.abspath(__file__))

        files = [f for f in os.listdir(current_dir) if f.lower().endswith(('.csv', '.txt'))]
        for f in files:
            path = os.path.join(current_dir, f)
            fname = f.lower()
            if "bosch_acronyms" in fname and not primary_db: primary_db = path
            elif "ai_translated" in fname and not ai_db: ai_db = path
            elif fname.endswith('.csv') and not primary_db: primary_db = path
        if not ai_db:
            target = os.path.join(current_dir, "missing_translated.txt")
            if os.path.exists(target): ai_db = target
    except: pass
    return primary_db, ai_db

def clean_key(text):
    if not text: return ""
    return re.sub(r'[^a-zA-Z0-9_]', '', text).strip().upper()

def safe_xml(text):
    if not text: return ""
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;').replace("'", '&apos;')

def load_dict(file_path):
    d = {}
    if not file_path or not os.path.exists(file_path): return d
    try:
        with open(file_path, mode='r', encoding='utf-8-sig') as f:
            sample = f.read(2048); f.seek(0)
            delimiter = ';' if ';' in sample else ','
            if 'Acronym' in sample:
                reader = csv.DictReader(f, delimiter=delimiter)
                for row in reader:
                    if 'Acronym' in row and 'Description' in row:
                        d[clean_key(row['Acronym'])] = row['Description'].strip()
            else:
                for line in f:
                    if delimiter in line:
                        parts = line.strip().split(delimiter, 1)
                        d[clean_key(parts[0])] = parts[1].strip()
    except: pass
    return d

def smart_match(title, d_main, d_ai):
    target = clean_key(title)
    if not target: return None, False
    keys = [target]
    parts = target.split('_')
    for i in range(len(parts)-1, 0, -1): keys.append("_".join(parts[:i]))
    for k in keys:
        if k in d_main: return d_main[k], False
        if k in d_ai: return f"AI: {d_ai[k]}", True
    return None, False

def run_translation():
    xdf_files = listbox_xdf.get(0, tk.END)
    csv_path = ent_csv.get()
    ai_path = ent_ai.get()
    if not xdf_files or not csv_path:
        messagebox.showwarning("Input Error", "Please select XDF file(s) and the Primary Database.")
        return
    try:
        d_main = load_dict(csv_path); d_ai = load_dict(ai_path)
        total_processed_files = 0
        all_missing_desc = {}; all_missing_none = set()

        for xdf_path in xdf_files:
            xdf_path = xdf_path.strip('{}')
            with open(xdf_path, mode='r', encoding='iso-8859-1') as f:
                content = f.read()

            def process(title, desc):
                raw_desc = desc if desc else ""
                c_desc = html.unescape(raw_desc.strip()).replace('&#224;', 'à').replace('&#225;', 'á')
                is_empty = not c_desc or c_desc.upper() == title.strip().upper()
                res, is_ai = smart_match(title, d_main, d_ai)
                if res: return res, c_desc, True
                else:
                    key = clean_key(title)
                    if not is_empty: all_missing_desc[key] = c_desc
                    else: all_missing_none.add(key)
                    return None, None, False

            if "<?xml" not in content and "<XDFFORMAT" not in content:
                segments = re.split(r'(%%END%%)', content)
                new_segments = []
                for seg in segments:
                    m = re.search(r'(020005|040005)\s+Title\s*=\s*"([^"]+)"', seg, re.IGNORECASE)
                    if m:
                        pre = m.group(1)[:2]
                        dm = re.search(f'{pre}0010\\s+Desc\\s*=\\s*"([^"]*)"', seg, re.IGNORECASE)
                        new_t, old_d, ok = process(m.group(2), dm.group(1) if dm else "")
                        if ok:
                            seg = re.sub(f'({pre}0010\\s+Desc\\s*=\\s*)(".*?")', lambda x: f'{x.group(1)}"{new_t}   |   {old_d}"', seg, flags=re.IGNORECASE)
                            seg = re.sub(f'({pre}0011\\s+DescSize\\s*=\\s*)0x[0-9A-F]+', lambda x: f'{x.group(1)}0x{len(new_t)+3+len(old_d):X}', seg, flags=re.IGNORECASE)
                    new_segments.append(seg)
                content = "".join(new_segments)
            else:
                content = content.replace('encoding="UTF-8"', 'encoding="iso-8859-1"')
                pattern = re.compile(r'<title>([^<]+)</title>\s*<description>([^<]*)</description>', re.DOTALL | re.IGNORECASE)
                def xml_sub(m):
                    t_val = m.group(1).strip(); d_val = m.group(2).strip()
                    new_t, old_d, ok = process(t_val, d_val)
                    if ok: return f"<title>{t_val}</title>\n    <description>{safe_xml(new_t)}&#013;&#010;{safe_xml(old_d)}</description>"
                    return m.group(0)
                content = pattern.sub(xml_sub, content)

            out_name = f"{os.path.splitext(xdf_path)[0]}_translated.xdf"
            with open(out_name, 'w', encoding='iso-8859-1', errors='ignore') as f: f.write(content)
            total_processed_files += 1

        # Určení cesty pro výstupní TXT - vždy vedle EXE/skriptu
        if getattr(sys, 'frozen', False):
            base_folder = os.path.dirname(sys.executable)
        else:
            base_folder = os.path.dirname(os.path.abspath(__file__))

        # Zápis chybějících popisů
        missing_desc_path = os.path.join(base_folder, "missing_descriptions.txt")
        with open(missing_desc_path, "w", encoding="utf-8") as f:
            for k, v in sorted(all_missing_desc.items()): 
                f.write(f"{k};{v}\n")
        
        # Zápis hesel bez informací
        missing_none_path = os.path.join(base_folder, "missing_no_info.txt")
        with open(missing_none_path, "w", encoding="utf-8") as f:
            for k in sorted(all_missing_none): 
                f.write(f"{k}\n")

        messagebox.showinfo("Batch Success", 
                            f"Processed {total_processed_files} file(s).\n\n"
                            f"Missing files updated in:\n{base_folder}\n\n"
                            f"Stats:\n- With Desc: {len(all_missing_desc)}\n- No Info: {len(all_missing_none)}")
    except Exception as e: messagebox.showerror("Error", str(e))

def handle_drop(event):
    files = listbox_xdf.tk.splitlist(event.data)
    for f in files:
        if f.lower().endswith('.xdf'): listbox_xdf.insert(tk.END, f)

# --- GUI ---
root = TkinterDnD.Tk(); root.title("Bosch XDF Translator"); root.geometry("620x750"); root.configure(bg="#f5f5f5")
root.minsize(500, 650)

icon_file = resource_path("favicon.ico")
if os.path.exists(icon_file): root.iconbitmap(icon_file)

style = ttk.Style(); style.theme_use('clam')
main_frame = tk.Frame(root, bg="#f5f5f5", padx=25, pady=20)
main_frame.pack(expand=True, fill="both")

# --- XDF SECTION (Responsive) ---
tk.Label(main_frame, text="Selected XDF Files (Drag & Drop):", bg="#f5f5f5", font=("Arial", 9, "bold")).pack(anchor="w")
list_container = tk.Frame(main_frame, bg="#f5f5f5")
list_container.pack(expand=True, fill="both", pady=(0, 5))

scrollbar = ttk.Scrollbar(list_container)
scrollbar.pack(side="right", fill="y")
listbox_xdf = tk.Listbox(list_container, font=("Arial", 8), yscrollcommand=scrollbar.set)
listbox_xdf.pack(side="left", expand=True, fill="both")
scrollbar.config(command=listbox_xdf.yview)

listbox_xdf.drop_target_register(DND_FILES)
listbox_xdf.dnd_bind('<<Drop>>', handle_drop)

list_btns = tk.Frame(main_frame, bg="#f5f5f5")
list_btns.pack(fill="x")
ttk.Button(list_btns, text="Clear List", command=lambda: listbox_xdf.delete(0, tk.END)).pack(side="left")
ttk.Button(list_btns, text="Add Files...", command=lambda: [listbox_xdf.insert(tk.END, f) for f in filedialog.askopenfilenames(filetypes=[("XDF files", "*.xdf")])]).pack(side="right")

ttk.Separator(main_frame, orient='horizontal').pack(fill='x', pady=15)

# --- DATABASE SECTION ---
m_db, a_db = find_databases()
def update_labels():
    p = ent_csv.get(); a = ent_ai.get()
    lbl_p.config(text="✓ Primary DB Loaded" if (p and os.path.exists(p)) else "✖ Primary DB Missing", fg="green" if (p and os.path.exists(p)) else "red")
    lbl_a.config(text="✓ AI Supplement Loaded" if (a and os.path.exists(a)) else "✖ AI Supplement Missing", fg="green" if (a and os.path.exists(a)) else "orange")

tk.Label(main_frame, text="Primary Database (CSV):", bg="#f5f5f5", font=("Arial", 9, "bold")).pack(anchor="w")
ent_csv = ttk.Entry(main_frame, width=70); ent_csv.pack(fill="x")
if m_db: ent_csv.insert(0, m_db)
lbl_p = tk.Label(main_frame, bg="#f5f5f5", font=("Arial", 8)); lbl_p.pack(anchor="w")
ttk.Button(main_frame, text="Change Primary...", command=lambda: (fn := filedialog.askopenfilename()) and (ent_csv.delete(0, tk.END), ent_csv.insert(0, fn), update_labels())).pack(anchor="e")

tk.Label(main_frame, text="AI Supplement (AI_translated):", bg="#f5f5f5", font=("Arial", 9, "bold")).pack(anchor="w", pady=(10, 0))
ent_ai = ttk.Entry(main_frame, width=70); ent_ai.pack(fill="x")
if a_db: ent_ai.insert(0, a_db)
lbl_a = tk.Label(frame if 'frame' in locals() else main_frame, bg="#f5f5f5", font=("Arial", 8)); lbl_a.pack(anchor="w")
ttk.Button(main_frame, text="Change AI...", command=lambda: (fn := filedialog.askopenfilename()) and (ent_ai.delete(0, tk.END), ent_ai.insert(0, fn), update_labels())).pack(anchor="e")

btn_run = tk.Button(main_frame, text="START BATCH TRANSLATION", command=run_translation, bg="#1B5E20", fg="white", font=("Arial", 11, "bold"), relief="flat", height=2)
btn_run.pack(fill="x", pady=20)

# --- CREDIT SECTION ---
ttk.Separator(main_frame, orient='horizontal').pack(fill='x', pady=10)
credit_frame = tk.Frame(main_frame, bg="#f5f5f5")
credit_frame.pack(fill="x")
tk.Label(credit_frame, text="Powered by Gemini AI (Google)", font=("Arial", 9), fg="#5dade2", bg="#f5f5f5").pack()
tk.Label(credit_frame, text="Created by Aleš Veigend", font=("Arial", 10, "bold"), bg="#f5f5f5").pack()
tk.Label(credit_frame, text="AlesVeigend@hotmail.cz", font=("Arial", 9), bg="#f5f5f5").pack()
tk.Label(credit_frame, text="Version 1.0 | 2026", font=("Arial", 9), fg="gray", bg="#f5f5f5").pack()

update_labels()
root.mainloop()
