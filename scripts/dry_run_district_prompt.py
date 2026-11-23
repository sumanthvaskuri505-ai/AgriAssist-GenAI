"""Dry run: shows the advisory prompt with and without district data,
WITHOUT calling OpenAI. Uses a dummy key and a fake client."""
import os
import sys
from importlib import import_module
from pathlib import Path

os.environ["OPENAI_API_KEY"] = "dummy-key-for-dry-run"   # your real key is never used
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = Path(__file__).resolve().parent.parent
os.chdir(BASE)                         # the app uses relative paths
sys.path.insert(0, str(BASE / "src"))

rag_mod = import_module("09_full_rag_pipeline")
district_mod = import_module("district_context")


class _Msg:
    def __init__(self, c):
        self.content = c


class _Choice:
    def __init__(self, c):
        self.message = _Msg(c)


class _Resp:
    def __init__(self, c):
        self.choices = [_Choice(c)]


class _Completions:
    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return _Resp("[dry run - the model was not called]")


class _Chat:
    def __init__(self):
        self.completions = _Completions()


class FakeClient:
    def __init__(self):
        self.chat = _Chat()


fake = FakeClient()
rag_mod.client = fake
rag = rag_mod.AgriculturalRAG(rag_mod.KB_PATH)

QUERY = "paddy leaves turning yellow in kharif"
baseline = {"prompt": None}


def run(label, code):
    text = district_mod.build_context_text(code) if code else ""
    calls = fake.chat.completions.calls
    before = len(calls)
    result = rag.generate_advisory(QUERY, top_k=5, district_context=text)

    print("=" * 70)
    print(label)
    print("district_context_used flag:", result.get("district_context_used"))
    print("documents retrieved:", len(result["retrieved_documents"]))
    if len(calls) == before:
        print("The model would not be called (no documents retrieved).")
        return

    prompt = calls[-1]["messages"][1]["content"]
    print("prompt length (characters):", len(prompt))
    print("contains 'DISTRICT DATA':", "DISTRICT DATA" in prompt)

    if not text:
        baseline["prompt"] = prompt
        i = prompt.index("Region:")
        print("--- prompt around the Region line ---")
        print(prompt[i:i + 60])
        return

    start = prompt.index("DISTRICT DATA")
    end = prompt.index("Retrieved Evidence:")
    print("--- district part of the prompt ---")
    print(prompt[start:end])
    without = prompt[:start] + prompt[end:]
    same = baseline["prompt"] is not None and without == baseline["prompt"]
    print("Prompt identical to the no-district prompt once the district block is removed:", same)


run("1. NO DISTRICT (baseline)", None)
run("2. NIZAMABAD (code 516)", 516)
run("3. HYDERABAD (code 507)", 507)
print("=" * 70)
print("Dry run finished. The model was never called.")