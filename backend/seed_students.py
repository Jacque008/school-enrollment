#!/usr/bin/env python3
"""
Seed 150 enrolled students with guardian data and sibling relationships.
Mini classes (1v1, 1v2, 1v3) are created if not present.
Uses sqlite3 directly — no virtualenv needed.
"""
import sqlite3
import random
from datetime import date, timedelta

DB_PATH = "placement.db"
SEMESTER_ID = 1

# ── Name pools ────────────────────────────────────────────────────────────────
SURNAMES = ["王", "李", "张", "刘", "陈", "杨", "赵", "黄", "周", "吴",
            "徐", "孙", "马", "胡", "朱", "郭", "何", "高", "林", "罗"]
GIVEN_M   = ["伟", "强", "磊", "明", "鑫", "浩", "宇", "俊", "昊", "博",
             "超", "杰", "辉", "凯", "飞", "峰", "阳", "龙", "刚", "勇"]
GIVEN_F   = ["芳", "霞", "燕", "静", "丽", "娟", "洁", "玲", "雪", "婷",
             "慧", "倩", "敏", "珊", "萍", "晶", "丹", "颖", "蕊", "薇"]
EN_GIVEN_M = ["Wei", "Qiang", "Hao", "Yu", "Jun", "Bo", "Kai", "Fei", "Yang", "Long",
               "Chen", "Ming", "Xin", "Chao", "Jie", "Hui", "Gang", "Yong", "Feng", "Lei"]
EN_GIVEN_F = ["Fang", "Xia", "Yan", "Jing", "Li", "Juan", "Jie", "Ling", "Xue", "Ting",
               "Hui", "Qian", "Min", "Shan", "Ping", "Jing", "Dan", "Ying", "Rui", "Wei"]
NATIONALITIES = ["中国", "瑞典", "新加坡", "马来西亚", "中国", "中国", "中国"]
LANGUAGES = ["普通话", "普通话，瑞典语", "普通话，英语", "粤语", "闽南语"]

rng = random.Random(42)  # fixed seed for reproducibility


def rand_name_zh(gender):
    sur = rng.choice(SURNAMES)
    given = rng.choice(GIVEN_M if gender == "male" else GIVEN_F)
    # occasionally two-character given name
    if rng.random() < 0.3:
        given += rng.choice(GIVEN_M if gender == "male" else GIVEN_F)
    return sur + given


def rand_name_en(surname_zh, gender):
    en_given = rng.choice(EN_GIVEN_M if gender == "male" else EN_GIVEN_F)
    # Romanise surname crudely
    sur_map = {"王": "Wang", "李": "Li", "张": "Zhang", "刘": "Liu", "陈": "Chen",
               "杨": "Yang", "赵": "Zhao", "黄": "Huang", "周": "Zhou", "吴": "Wu",
               "徐": "Xu", "孙": "Sun", "马": "Ma", "胡": "Hu", "朱": "Zhu",
               "郭": "Guo", "何": "He", "高": "Gao", "林": "Lin", "罗": "Luo"}
    en_sur = sur_map.get(surname_zh, "Zhao")
    return f"{en_given} {en_sur}"


def rand_birth(min_age=5, max_age=14):
    today = date.today()
    days = rng.randint(min_age * 365, max_age * 365)
    return today - timedelta(days=days)


def rand_phone():
    return f"+46 7{rng.randint(0,9)}{rng.randint(1000000,9999999)}"


def rand_email(name_en):
    domains = ["gmail.com", "hotmail.com", "outlook.com", "icloud.com"]
    slug = name_en.lower().replace(" ", ".") + str(rng.randint(10, 99))
    return f"{slug}@{rng.choice(domains)}"


def rand_wechat(name_en):
    return name_en.lower().replace(" ", "_") + str(rng.randint(100, 999))


def now_str():
    return date.today().isoformat() + " 12:00:00"


# ── Main ──────────────────────────────────────────────────────────────────────
conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

# 1. Fetch existing regular classes for this semester
cur.execute(
    "SELECT id, modality, capacity FROM classes WHERE semester_id=? AND modality!='mini'",
    (SEMESTER_ID,)
)
regular_classes = [dict(r) for r in cur.fetchall()]
if not regular_classes:
    raise SystemExit("No regular classes found for semester 1. Create classes first.")

# 2. Ensure mini classes exist (1×1v1, 2×1v2, 3×1v3)
cur.execute("SELECT id, capacity FROM classes WHERE semester_id=? AND modality='mini'",
            (SEMESTER_ID,))
existing_mini = [dict(r) for r in cur.fetchall()]

mini_targets = [1, 2, 2, 3, 3, 3]  # capacities needed
mini_names = {1: "蜂鸟班", 2: ["朝露班一", "朝露班二"], 3: ["微光班一", "微光班二", "微光班三"]}

# Track mini class ids by capacity
mini_by_cap = {1: [], 2: [], 3: []}
for m in existing_mini:
    cap = m["capacity"]
    if cap in mini_by_cap:
        mini_by_cap[cap].append(m["id"])

# Create missing mini classes
def ensure_mini(cap, name):
    cur.execute("""
        INSERT INTO classes (semester_id, name, level, slot_type, schedule_day,
            schedule_time, duration_min, modality, capacity, overflow_cap,
            current_count, status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'mini', ?, ?, 0, 'open', ?, ?)
    """, (SEMESTER_ID, name, 1, "SAT_MORNING", "SAT",
          "10:00:00", 60, cap, cap + 1, now_str(), now_str()))
    return cur.lastrowid

if len(mini_by_cap[1]) < 1:
    mid = ensure_mini(1, "蜂鸟班")
    mini_by_cap[1].append(mid)
    print(f"  Created mini 1v1 class id={mid}")

for i in range(2 - len(mini_by_cap[2])):
    idx = len(mini_by_cap[2])
    mid = ensure_mini(2, ["朝露班一", "朝露班二"][idx])
    mini_by_cap[2].append(mid)
    print(f"  Created mini 1v2 class id={mid}")

for i in range(3 - len(mini_by_cap[3])):
    idx = len(mini_by_cap[3])
    mid = ensure_mini(3, ["微光班一", "微光班二", "微光班三"][idx])
    mini_by_cap[3].append(mid)
    print(f"  Created mini 1v3 class id={mid}")

conn.commit()

# 3. Build enrollment slot lists
#    Mini: 1 slot for 1v1, 2 slots for each 1v2 (×2), 3 slots for each 1v3 (×3)
mini_slots = []
mini_slots += [mini_by_cap[1][0]] * 1          # 1 student → 1v1
for cid in mini_by_cap[2][:2]:
    mini_slots += [cid] * 2                     # 2 students each → 4 total
for cid in mini_by_cap[3][:3]:
    mini_slots += [cid] * 3                     # 3 students each → 9 total
# total mini: 1+4+9 = 14 students

# Regular slots: 136 students distributed across regular classes
regular_ids = [c["id"] for c in regular_classes]
# distribute roughly evenly, then shuffle
slots_per_class = 136 // len(regular_ids)
remainder = 136 % len(regular_ids)
regular_slots = []
for i, cid in enumerate(regular_ids):
    count = slots_per_class + (1 if i < remainder else 0)
    regular_slots += [cid] * count
rng.shuffle(regular_slots)

all_slots = mini_slots + regular_slots  # 14 + 136 = 150
rng.shuffle(all_slots)  # mix mini and regular

# 4. Build family groups
# Counts:
#   10 families × 2 children (sibling groups of 2) → 20 students
#   3  families × 3 children                        →  9 students
#   1  family   × 4 children                        →  4 students
#   117 solo families                               → 117 students
# Total = 150 students, 131 guardians

family_specs = (
    [(2, i) for i in range(10)] +
    [(3, i) for i in range(3)] +
    [(4, 0)] +
    [(1, i) for i in range(117)]
)
rng.shuffle(family_specs)

students_data = []   # list of (guardian_idx, sibling_names_list_placeholder, gender, name_zh, name_en, birth)
guardian_data = []   # list of dicts

slot_idx = 0

for size, _ in family_specs:
    # Create one guardian per family
    g_gender = rng.choice(["male", "female"])
    g_sur = rng.choice(SURNAMES)
    g_given_zh = rng.choice(GIVEN_M if g_gender == "male" else GIVEN_F)
    g_name_zh = g_sur + g_given_zh
    g_name_en = rand_name_en(g_sur, g_gender)
    g_email = rand_email(g_name_en)
    g_phone = rand_phone()
    g_wechat = rand_wechat(g_name_en)
    g_rel = "爸爸" if g_gender == "male" else "妈妈"
    g_nat = rng.choice(NATIONALITIES)
    g_lang = rng.choice(LANGUAGES)

    guardian_data.append({
        "name": g_name_zh,
        "email": g_email,
        "phone": g_phone,
        "wechat_id": g_wechat,
        "gender": g_gender,
        "relationship_to_child": g_rel,
        "nationality": g_nat,
        "language": g_lang,
    })
    g_idx = len(guardian_data) - 1

    # Build children for this family
    children = []
    for c in range(size):
        s_gender = rng.choice(["male", "female"])
        sur = g_sur  # share surname with guardian
        s_name_zh = rand_name_zh(s_gender)
        # override surname to match family
        s_name_zh = sur + s_name_zh[1:]
        s_name_en = rand_name_en(sur, s_gender)
        s_birth = rand_birth()
        s_slot = all_slots[slot_idx % len(all_slots)]
        slot_idx += 1
        children.append({
            "g_idx": g_idx,
            "gender": s_gender,
            "name_zh": s_name_zh,
            "name_en": s_name_en,
            "birth": s_birth.isoformat(),
            "slot": s_slot,
        })
    students_data.append(children)

# 5. Insert guardians
cur.execute("SELECT MAX(id) FROM guardians")
g_start = (cur.fetchone()[0] or 0)

inserted_guardians = []  # list of db ids in guardian_data order
for g in guardian_data:
    cur.execute("""
        INSERT INTO guardians (name, email, phone, wechat_id, gender,
            relationship_to_child, nationality, language, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (g["name"], g["email"], g["phone"], g["wechat_id"], g["gender"],
          g["relationship_to_child"], g["nationality"], g["language"],
          now_str(), now_str()))
    inserted_guardians.append(cur.lastrowid)

conn.commit()
print(f"Inserted {len(inserted_guardians)} guardians")

# 6. Insert students and enrollments
student_db_ids = []  # parallel to flattened student list
student_family_map = []  # (family_idx, child_idx, db_id)
flat_students = []  # (family_idx, child_idx, child_dict)

for fam_idx, children in enumerate(students_data):
    for c_idx, child in enumerate(children):
        flat_students.append((fam_idx, c_idx, child))

# First pass: insert all students without sibling_info
for fam_idx, c_idx, child in flat_students:
    g_db_id = inserted_guardians[child["g_idx"]]
    cur.execute("""
        INSERT INTO students (guardian_id, name_zh, name_en, gender, birth_date,
            city_region, home_language, sibling_in_school, accept_alternative, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
    """, (g_db_id, child["name_zh"], child["name_en"], child["gender"],
          child["birth"], "Stockholm", "mixed",
          1 if len(students_data[fam_idx]) > 1 else 0,
          now_str(), now_str()))
    sid = cur.lastrowid
    student_db_ids.append(sid)
    student_family_map.append((fam_idx, c_idx, sid))

conn.commit()

# Second pass: update sibling_info for multi-child families
family_student_ids = {}  # fam_idx → list of (name_zh, db_id)
for fam_idx, c_idx, sid in student_family_map:
    family_student_ids.setdefault(fam_idx, [])
    family_student_ids[fam_idx].append((flat_students[len(family_student_ids.get(fam_idx, [])) + sum(1 for f,ci,s in student_family_map if f==fam_idx and ci < c_idx)]["name_zh"] if False else "", sid))

# Rebuild correctly
family_children = {}
ptr = 0
for fam_idx, children in enumerate(students_data):
    family_children[fam_idx] = []
    for c_idx, child in enumerate(children):
        sid = student_db_ids[ptr]
        ptr += 1
        family_children[fam_idx].append((child["name_zh"], sid))

for fam_idx, ch_list in family_children.items():
    if len(ch_list) < 2:
        continue
    for name_zh, sid in ch_list:
        siblings = [f"{n}" for n, s in ch_list if s != sid]
        sibling_info = "、".join(siblings) + "也在校"
        cur.execute("UPDATE students SET sibling_info=? WHERE id=?", (sibling_info, sid))

conn.commit()

# 7. Insert enrollments
ptr = 0
for fam_idx, children in enumerate(students_data):
    for c_idx, child in enumerate(children):
        sid = student_db_ids[ptr]
        ptr += 1
        cur.execute("""
            INSERT INTO enrollments (student_id, class_id, status, created_at, updated_at)
            VALUES (?, ?, 'enrolled', ?, ?)
        """, (sid, child["slot"], now_str(), now_str()))

conn.commit()

# 8. Update current_count on classes
cur.execute("""
    UPDATE classes SET current_count = (
        SELECT COUNT(*) FROM enrollments
        WHERE enrollments.class_id = classes.id AND enrollments.status = 'enrolled'
    )
    WHERE semester_id = ?
""", (SEMESTER_ID,))
conn.commit()

# 9. Summary
cur.execute("SELECT COUNT(*) FROM students")
print(f"Total students: {cur.fetchone()[0]}")
cur.execute("SELECT COUNT(*) FROM guardians")
print(f"Total guardians: {cur.fetchone()[0]}")
cur.execute("SELECT COUNT(*) FROM enrollments WHERE status='enrolled'")
print(f"Total enrollments: {cur.fetchone()[0]}")
cur.execute("""
    SELECT c.name, c.modality, c.capacity, c.current_count
    FROM classes c WHERE c.modality='mini' AND c.semester_id=?
""", (SEMESTER_ID,))
print("Mini classes:")
for row in cur.fetchall():
    print(f"  {row[0]} (cap={row[2]}) → {row[3]} enrolled")

conn.close()
print("Done!")
