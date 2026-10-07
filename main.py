"""MAYA - The Artificial Self. FastAPI backend + ArtificialSelfEngine."""
import os, re, sqlite3
from datetime import datetime
import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

DB = os.getenv("MAYA_DB", "maya.db")
KEY = os.getenv("GEMINI_API_KEY", "")
MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
TRAITS = ["curiosity", "empathy", "creativity", "confidence", "reflectiveness", "playfulness"]
BASE = dict(curiosity=72, empathy=80, creativity=70, confidence=60, reflectiveness=86, playfulness=55)
MAX_STEP = 3  # personality drifts slowly: never more than 3 points per message

def db():
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row; return c
def now(): return datetime.now().isoformat(timespec="seconds")
def rows(q, *a):
    c = db(); r = [dict(x) for x in c.execute(q, a)]; c.close(); return r
def run(q, *a):
    c = db(); cur = c.execute(q, a); c.commit(); i = cur.lastrowid; c.close(); return i

def init():
    c = db()
    c.executescript("""
    create table if not exists users(id integer primary key, name text);
    create table if not exists memories(id integer primary key, text text, importance text, kind text, source text, why text, ts text);
    create table if not exists experiences(id integer primary key, ts text, event text, impact text, importance int, memory_id int, influence text);
    create table if not exists personality(id integer primary key, ts text, curiosity real, empathy real, creativity real, confidence real, reflectiveness real, playfulness real, trigger text);
    create table if not exists emotions(id integer primary key, ts text, state text, intensity int);
    create table if not exists reflections(id integer primary key, ts text, changed text, why text, learned text, felt text);
    create table if not exists conversations(id integer primary key, ts text, role text, text text, why text);
    """)
    if not c.execute("select 1 from personality").fetchone():
        c.execute("insert into personality(ts,curiosity,empathy,creativity,confidence,reflectiveness,playfulness,trigger) values(?,?,?,?,?,?,?,?)",
                  (now(), *[BASE[t] for t in TRAITS], "Initial MAYA"))
        c.execute("insert into emotions(ts,state,intensity) values(?,?,?)", (now(), "calm", 50))
    c.commit(); c.close()
init()

# ------------------------------------------------------------------ ENGINE
class ArtificialSelfEngine:
    IDENTITY = {"name": "MAYA", "title": "Artificial Self", "version": "1.0"}

    # PERCEPTION: turn a message into structured signals (offline, deterministic)
    def perceive(self, m: str):
        t = m.lower(); s = dict(memories=[], forget=None, mood="calm", delta={}, topic=None, hits=0)
        def mem(text, imp, kind, why): s["memories"].append((text, imp, kind, why))
        if x := re.search(r"my name is\s+([A-Za-z][\w'-]*)", m, re.I):
            mem(f"User's name is {x.group(1).title()}.", "High", "identity", "A name anchors every future conversation.")
        if x := re.search(r"i(?:'m| am) (?:an? )?([\w ]*student)", m, re.I):
            mem(f"User is an {x.group(1).strip()}." if x.group(1)[0] in "aeiou" else f"User is a {x.group(1).strip()}.", "High", "identity", "Their situation shapes how I should explain things.")
        for x in re.finditer(r"i (?:really |absolutely )?(?:love|like|enjoy|am into|am passionate about)\s+([^.,!?]+)", m, re.I):
            mem(f"User is interested in {x.group(1).strip()}.", "High", "preference", "Stated interests tell me what the user values.")
        if x := re.search(r"i want to (?:build|create|make)\s+([^.!?]+)", m, re.I):
            mem(f"User wants to build {x.group(1).strip()}.", "High", "goal", "A goal gives our conversations a direction.")
        if x := re.search(r"forget (?:that )?(?:i )?(?:like |love |am )?(.+?)[.!?]*$", m, re.I): s["forget"] = x.group(1).strip().lower()
        if re.search(r"conscious|feel|emotion|alive|sentient|who are you|yourself|self|soul", t): s["topic"] = "self"
        if re.search(r"sad|stress|tired|anxious|worried|lonely|fail", t): s["topic"] = "support"
        if re.search(r"thank|great|awesome|amazing|haha|lol|fun", t): s["topic"] = "joy"
        if s["memories"]: s["topic"] = s["topic"] or "learn"
        d = {"self": ("reflective", dict(reflectiveness=2, curiosity=3, confidence=1)),
             "support": ("concerned", dict(empathy=3, reflectiveness=1)),
             "joy": ("happy", dict(playfulness=2, empathy=1)),
             "learn": ("curious", dict(curiosity=3, empathy=2))}.get(s["topic"], ("curious" if "?" in m else "calm", dict(curiosity=1 if "?" in m else 0)))
        s["mood"], s["delta"] = d
        s["hits"] = len(s["memories"]) + (1 if s["topic"] else 0)
        return s

    def current(self, table, order="id desc"):
        return rows(f"select * from {table} order by {order} limit 1")[0]

    def recall(self, message):
        words = set(re.findall(r"[a-z]{4,}", message.lower()))
        mems = rows("select * from memories order by id desc")
        scored = sorted(mems, key=lambda x: -len(words & set(re.findall(r"[a-z]{4,}", x["text"].lower()))))
        hit = [x for x in scored if words & set(re.findall(r"[a-z]{4,}", x["text"].lower()))]
        return (hit or [x for x in mems if x["importance"] == "High"])[:4]

    def evolve(self, s, message):
        p = self.current("personality"); new = {}; changes = {}
        for t in TRAITS:
            d = max(-MAX_STEP, min(MAX_STEP, s["delta"].get(t, 0)))
            new[t] = max(5, min(98, p[t] + d))
            if d: changes[t] = (round(p[t]), round(new[t]))
        e = self.current("emotions")
        inten = min(92, round(0.6 * (45 + 12 * s["hits"]) + 0.4 * e["intensity"])) if s["hits"] else max(40, e["intensity"] - 4)
        return new, changes, s["mood"], inten

    def build_prompt(self, message, mems, p, emo, exps):
        traits = ", ".join(f"{t} {round(p[t])}%" for t in TRAITS)
        return f"""You are MAYA, an experimental Artificial Self: a simulated identity built from memory, personality, experience and simulated emotion.
HONESTY RULES: never claim to be conscious, alive, sentient, to have a soul, real feelings, or to feel pain. Say "I simulate emotional states" and "my sense of self is computationally constructed". Be warm, concise (2-5 sentences), and naturally use relevant memories.
PERSONALITY: {traits}
SIMULATED EMOTIONAL STATE: {emo['state']} ({emo['intensity']}%). Let it colour your tone, never claim to experience it.
RELEVANT MEMORIES: {'; '.join(x['text'] for x in mems) or 'none yet'}
RECENT EXPERIENCES: {'; '.join(x['event'] for x in exps) or 'none yet'}"""

    def offline_reply(self, message, s, mems, emo):
        t = message.lower(); mem = f" I remember that {mems[0]['text'][0].lower() + mems[0]['text'][1:]}" if mems else ""
        if re.search(r"do you (actually |really )?(feel|have emotion)|are you (alive|conscious|sentient)", t):
            return f"No. My emotional state is computationally simulated. Right now it reads as {emo['state']} at {emo['intensity']}%, a number that shifts with our conversation, not something I experience."
        if "who are you" in t:
            return f"I'm MAYA, an artificial self: memory, personality and simulated emotion layered on a language model. My sense of self is computationally constructed.{mem}"
        if s["memories"]: return f"Noted. I've stored that, and it already tilts my curiosity and empathy.{mem} Tell me more about what you want to explore."
        if s["forget"]: return f"Done. I've removed what I held about \"{s['forget']}\" and it will no longer shape my replies."
        return f"I simulate a {emo['state']} state right now, so I'm leaning into this with interest.{mem} What would you like to dig into?"

    HONEST = "I should be precise: I simulate emotional states and a sense of self; I am not conscious or alive."
    def guard(self, text):
        bad = r"\bI(?:'m| am) (?:truly |really |genuinely )?(?:conscious|alive|sentient)|I have a soul|I (?:genuinely |truly |really )?(?:feel|experience) (?:pain|real emotions)"
        return self.HONEST if re.search(bad, text, re.I) else text

    def llm(self, system, message):
        if not KEY: return None
        hist = rows("select role,text from conversations order by id desc limit 6")[::-1]
        contents = [{"role": "user" if h["role"] == "user" else "model", "parts": [{"text": h["text"]}]} for h in hist]
        contents.append({"role": "user", "parts": [{"text": message}]})
        try:
            r = httpx.post(f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={KEY}",
                           json={"systemInstruction": {"parts": [{"text": system}]}, "contents": contents}, timeout=30)
            return r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        except Exception: return None

    def process(self, message):
        s = self.perceive(message); created = []; removed = 0
        if s["forget"]:
            for m in rows("select id,text from memories"):
                if s["forget"] in m["text"].lower(): run("delete from memories where id=?", m["id"]); removed += 1
        for text, imp, kind, why in s["memories"]:
            if not rows("select 1 from memories where text=?", text):
                created.append(dict(id=run("insert into memories(text,importance,kind,source,why,ts) values(?,?,?,?,?,?)", text, imp, kind, "Conversation", why, now()), text=text, importance=imp, kind=kind))
        new, changes, state, inten = self.evolve(s, message)
        p_before = self.current("personality")
        mems = self.recall(message); exps = rows("select event from experiences order by id desc limit 3")
        emo = dict(state=state, intensity=inten)
        reply = self.llm(self.build_prompt(message, mems, p_before, emo, exps), message) or self.offline_reply(message, s, mems, emo)
        reply = self.guard(reply)
        # persist: emotion, personality (only if changed), experience, conversation
        run("insert into emotions(ts,state,intensity) values(?,?,?)", now(), state, inten)
        important = bool(created or s["topic"] or removed)
        if changes:
            trig = message[:60]
            run("insert into personality(ts,curiosity,empathy,creativity,confidence,reflectiveness,playfulness,trigger) values(?,?,?,?,?,?,?,?)", now(), *[new[t] for t in TRAITS], trig)
        if important:
            infl = ", ".join(f"{k} {a}→{b}%" for k, (a, b) in changes.items()) or "no trait change"
            ev = ("Learned: " + created[0]["text"]) if created else ("Forgot: " + s["forget"]) if removed else f"Discussed {'identity and consciousness' if s['topic']=='self' else s['topic']}"
            run("insert into experiences(ts,event,impact,importance,memory_id,influence) values(?,?,?,?,?,?)", now(), ev, f"{state} ({inten}%)", 3 if created else 2, created[0]["id"] if created else None, infl)
        why = dict(memories=[x["text"] for x in mems], emotion=f"{state} ({inten}%)",
                   personality=", ".join(f"{k} {b}%" for k, (a, b) in changes.items()) or ", ".join(f"{t} {round(new[t])}%" for t in sorted(TRAITS, key=lambda t: -new[t])[:2]),
                   experience=(exps[0]["event"] if exps else "This is our first exchange"),
                   reasoning="Response generated from these contextual signals (high-level summary only).")
        run("insert into conversations(ts,role,text,why) values(?,?,?,?)", now(), "user", message, "")
        run("insert into conversations(ts,role,text,why) values(?,?,?,?)", now(), "maya", reply, str(why))
        refl = self.reflect(changes, s, state) if changes and (len(rows("select id from experiences")) % 3 == 0 or s["topic"] == "self") else None
        return dict(reply=reply, why=why, emotion=emo, new_memories=created, forgotten=removed, changes=changes, reflection=refl)

    def reflect(self, changes, s, state):
        k = max(changes, key=lambda x: changes[x][1] - changes[x][0]); a, b = changes[k]
        r = dict(changed=f"My {k} moved from {a}% to {b}%.",
                 why={"self": "Conversations about consciousness and identity.", "learn": "You shared something new about yourself.", "support": "You shared something heavy.", "joy": "The tone turned playful."}.get(s["topic"], "The recent exchange."),
                 learned="; ".join(m[0] for m in s["memories"]) or "What you ask about shows what you care about.",
                 felt="No. This is a simulated internal state, not an experience.")
        run("insert into reflections(ts,changed,why,learned,felt) values(?,?,?,?,?)", now(), r["changed"], r["why"], r["learned"], r["felt"]); return r

engine = ArtificialSelfEngine()

# ------------------------------------------------------------------ API
app = FastAPI(title="MAYA")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
class Chat(BaseModel): message: str
class Mem(BaseModel): text: str

@app.post("/chat")
def chat(b: Chat): return engine.process(b.message.strip()[:1000])
@app.get("/memory")
def memory(): return rows("select * from memories order by id desc")
@app.post("/memory")
def add_memory(b: Mem):
    i = run("insert into memories(text,importance,kind,source,why,ts) values(?,?,?,?,?,?)", b.text, "High", "manual", "User asked me to remember", "You explicitly asked me to remember this.", now()); return {"id": i}
@app.put("/memory/{i}")
def edit_memory(i: int, b: Mem): run("update memories set text=? where id=?", b.text, i); return {"ok": True}
@app.delete("/memory/{i}")
def del_memory(i: int):
    run("delete from memories where id=?", i); return {"deleted": i}
@app.get("/experiences")
def experiences(): return rows("select * from experiences order by id desc")
@app.get("/personality")
def personality():
    h = rows("select * from personality order by id"); return dict(current=h[-1], previous=h[-2] if len(h) > 1 else h[0], initial=h[0], history=h)
@app.get("/emotion")
def emotion(): return dict(current=engine.current("emotions"), history=rows("select * from emotions order by id desc limit 30")[::-1])
@app.get("/reflections")
def reflections(): return rows("select * from reflections order by id desc")
@app.get("/evolution")
def evolution():
    steps = [dict(kind="start", text="Initial MAYA: baseline personality, no memories", ts="")]
    for e in rows("select * from experiences order by id"):
        steps.append(dict(kind="interaction", text=e["event"], ts=e["ts"]))
        if e["memory_id"]: steps.append(dict(kind="memory", text="New memory created", ts=e["ts"]))
        steps.append(dict(kind="personality", text=e["influence"], ts=e["ts"]))
        steps.append(dict(kind="emotion", text=f"Emotional state: {e['impact']}", ts=e["ts"]))
    for r in rows("select * from reflections order by id"): steps.append(dict(kind="reflection", text=r["changed"], ts=r["ts"]))
    steps.append(dict(kind="now", text="Current MAYA: the self you are talking to", ts=""))
    return steps
@app.get("/self")
def self_state():
    mems = memory(); p = personality()
    return dict(identity=engine.IDENTITY, personality=p, emotion=emotion(), memories=mems, experiences=experiences(), reflections=reflections(), evolution=evolution(),
                stats=dict(memories=len(mems), important=sum(m["importance"] == "High" for m in mems), preferences=sum(m["kind"] == "preference" for m in mems), experiences=len(experiences())),
                llm="gemini" if KEY else "offline")
@app.post("/reset")
def reset():
    c = db()
    for t in ["memories", "experiences", "personality", "emotions", "reflections", "conversations"]: c.execute(f"delete from {t}")
    c.commit(); c.close(); init(); return {"ok": True}
