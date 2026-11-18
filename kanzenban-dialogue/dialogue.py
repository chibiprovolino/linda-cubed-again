"""Rebuild LINDA.MIC with the Kanzenban dialogue draft applied to the v0.95.9 BIN."""
from pathlib import Path
import hashlib
import json
import re
import shutil
import struct
import sys
import textwrap

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import doctor_event as doctor

DRAFT = HERE / "english-dialogue-draft.md"
NAME = "dialogue-only"

def draft_entries():
    text = DRAFT.read_text(encoding="utf-8")
    markers = list(re.finditer(r"\*\*Saturn Japanese\*\* · \*\*(.*?)\*\*", text))
    entries = []
    for i, marker in enumerate(markers):
        end = markers[i + 1].start() if i + 1 < len(markers) else len(text)
        block = text[marker.end():end]
        draft = re.search(r"\*\*Saturn English · editable draft\*\*\s*\n(.*?)(?=\n\*\*|\n##|\Z)", block, re.S)
        if not draft:
            continue
        english = "\n".join(line.removeprefix("> ").removeprefix(">")
                            for line in draft[1].strip().splitlines()).strip()
        prior = text[:marker.start()]
        refs = list(re.finditer(r"\*\*(?:PlayStation counterpart[^\n]*|Related PlayStation[^\n]*)\*\* · `([^@]+)@0x([0-9A-F]+)`", prior))
        # A missing-counterpart annotation belongs to the current entry.
        no_match = prior.rfind("**PlayStation comparison**")
        ref = refs[-1] if refs and refs[-1].start() > no_match else None
        entries.append({"id": marker[1], "text": english,
                        "bank": ref[1] if ref else None,
                        "offset": int(ref[2], 16) if ref else None})
    return entries

def pointer_groups(prog):
    start = doctor.u16(prog, 2)
    stop = doctor.u16(prog, doctor.u16(prog, 0))
    pointers = []
    previous = 0
    for pos in range(start, stop, 2):
        value = doctor.u16(prog, pos)
        while value < previous:
            value += 65536
        pointers.append((pos, value))
        previous = value
    unique = sorted(set(p for _, p in pointers))
    groups = []
    for i, offset in enumerate(unique):
        end = unique[i + 1] if i + 1 < len(unique) else len(prog)
        raw = prog[offset:end]
        records = raw.split(b"\0")
        groups.append((offset, records))
    return pointers, groups

def encode(text):
    swaps = {"’": "'", "‘": "'", "“": '"', "”": '"', "…": "...", "—": "--",
             "–": "-", "■": "\x81\xa1", "♥": "\x81\xa1", "{garment}": "\x1d",
             "{age}": "\x1e", "〔…〕": "\x1d"}
    for old, new in swaps.items():
        text = text.replace(old, new)
    return text.encode("latin1")

def display(text, width=34, rows=3):
    pages = []
    for paragraph in re.split(r"\n\s*\n", text):
        lines = textwrap.wrap(paragraph.replace("\n", " "), width,
                              break_long_words=False, break_on_hyphens=False)
        pages.extend(b"\r".join(encode(line) for line in lines[i:i+rows])
                     for i in range(0, len(lines), rows))
    return b"\x0c" + b"\x12\r\x0c".join(pages)

def directory(archive):
    entries = []
    pos = 0
    while archive[pos]:
        name = archive[pos:pos+13].split(b"\0")[0]
        offset = int.from_bytes(archive[pos+13:pos+16], "little")
        entries.append((name, offset))
        pos += 16
    end = int.from_bytes(archive[pos+13:pos+16], "little")
    members = {}
    for i, (name, offset) in enumerate(entries):
        stop = entries[i+1][1] if i+1 < len(entries) else end
        members[name] = archive[offset:stop]
    return entries, end, members

def replace_program(archive, prog):
    entries, end, members = directory(archive)
    first = entries[0][1]
    assert entries[0][0] == b"PROG.BIN"
    prog += bytes((len(members[b"PROG.BIN"]) - len(prog)) % 4)
    parts = [prog] + [members[name] for name, _ in entries[1:]]
    header = bytearray(archive[:first])
    offset = first
    for i, part in enumerate(parts):
        header[i*16+13:i*16+16] = offset.to_bytes(3,"little")
        offset += len(part)
    header[len(parts)*16+13:len(parts)*16+16] = offset.to_bytes(3,"little")
    result = bytes(header) + b"".join(parts)
    return result + bytes((-len(result)) % 2048)

def original_record(bank, offset):
    prog = (ROOT / "orig" / bank / "PROG.BIN").read_bytes()
    return prog[offset:prog.index(0, offset)]

def assemble(prog, pointers, groups, extra_code=b""):
    result = bytearray(prog[:groups[0][0]]) + extra_code
    remap = {}
    for old, records in groups:
        remap[old] = len(result)
        result += b"\0".join(records)
    for location, target in pointers:
        struct.pack_into("<H", result, location, remap[target] & 65535)
    return bytes(result)

def build(source, output):
    entries = draft_entries()
    replacements = {}
    names = {}
    for entry in entries:
        if entry["id"].startswith("071@") or not entry["bank"]:
            continue
        key = original_record(entry["bank"], entry["offset"])
        replacements[key] = entry
        names[entry["id"]] = 0
    src = source.read_bytes()
    assert hashlib.sha256(src).hexdigest() == "e65fd247ede8cc7d22cc032e2875e6ef82e78a08cc8f69c56e7dac3cc7902cf3"
    def read(lba, n):
        raw = src[lba*2352:(lba+n)*2352]
        return b"".join(raw[i+24:i+2072] for i in range(0,len(raw),2352))
    toc = bytearray(read(387,35))
    directories = sorted(p for p in (ROOT/"orig").iterdir() if (p/"PROG.BIN").exists())
    slots = [i for i in range(768) if doctor.u32(toc,i*16+4)]
    assert len(slots)==len(directories)==413
    archives = []
    report = []
    for slot, origdir in zip(slots,directories):
        sector, count = struct.unpack_from("<II",toc,slot*16)
        archive = read(387+sector,count)
        _, _, members = directory(archive)
        stock = members[b"PROG.BIN"]
        jp = (origdir/"PROG.BIN").read_bytes()
        jp_pointers, jp_groups = pointer_groups(jp)
        pointers, groups = pointer_groups(stock)
        assert len(groups)==len(jp_groups),origdir.name
        changed = []
        for (offset, records), (jp_offset, jp_records) in zip(groups,jp_groups):
            # Atlas may leave padding at the end of the last text group.
            for idx, key in enumerate(jp_records):
                if not key: continue
                assert idx<len(records),(origdir.name,idx)
                old = records[idx]
                if key in replacements:
                    entry = replacements[key]
                    if b"\x83\x49\x81\x5b\x83\x7d\x83\x93" in key:
                        new = old.replace(b"Aumann",b"Koman").replace(b"AUMANN",b"KOMAN")
                    elif entry["id"]=="582@0x137F":
                        new = old  # Kept at the PS1 English wording.
                    elif entry["id"]=="397@0x50C0":
                        prose, choices = entry["text"].split("\n\n")
                        new = display(prose) + b"\x12\r\x0c" + b" / ".join(b"\x01"+encode(t)+b"\x0e" for t in choices.split(" / "))
                    else:
                        new = display(entry["text"])
                        if old.endswith(b"\x12"): new += b"\x12"
                    records[idx] = new
                    changed.append(entry["id"])
                    names[entry["id"]] += 1
                else:
                    renamed = old.replace(b"Aumann",b"Koman").replace(b"AUMANN",b"KOMAN")
                    if renamed != old:
                        records[idx] = renamed
                        changed.append("surname occurrence")
        if slot == 71:
            assert not changed, "Slot 71 is replaced separately by doctor_event"
        extra_code = b""
        if slot == 600:
            # Saturn initializes the numeric substitution with Kokubu's current age.
            # PS1 sysvar/string queue is +1 and year is D2 27 instead of D2 26.
            assert stock[0x9e8:0x9eb] == bytes.fromhex("a3 12 a0")
            patched = bytearray(stock)
            patched[0x9e8:0x9eb] = b"\xa1" + struct.pack("<H", groups[0][0])
            stock = bytes(patched)
            extra_code = bytes.fromhex("90 c2 33 b0 1e ff d2 27 ff 92 ef ff 9f eb e6 2c a3 12 a0")
        prog = assemble(stock,pointers,groups,extra_code) if changed else stock
        if changed:
            rebuilt = replace_program(archive,prog)
            _, _, checked = directory(rebuilt)
            assert all(checked[n]==v for n,v in members.items() if n!=b"PROG.BIN")
            archive = rebuilt
            report.append({"slot":slot,"bank":origdir.name,"records":changed})
        archives.append((slot,archive))
    missing=[key for key,n in names.items() if not n]
    assert not missing,missing
    # Append a complete rebuilt MIC extent so other disc files keep their LBAs.
    mic = bytearray(toc)
    for slot,archive in archives:
        struct.pack_into("<II",mic,slot*16,len(mic)//2048,len(archive)//2048)
        struct.pack_into("<I",mic,slot*16+12,doctor.checkword(archive))
        mic += archive
    start=len(src)//2352
    pvd=bytearray(read(16,1))
    struct.pack_into("<I",pvd,80,start+len(mic)//2048)
    struct.pack_into(">I",pvd,84,start+len(mic)//2048)
    iso=bytearray(read(23,1))
    pos=0
    while iso[pos]:
        name=iso[pos+33:pos+33+iso[pos+32]]
        if name==b"LINDA.MIC;1":
            struct.pack_into("<I",iso,pos+2,start)
            struct.pack_into(">I",iso,pos+6,start)
            struct.pack_into("<I",iso,pos+10,len(mic))
            struct.pack_into(">I",iso,pos+14,len(mic))
            break
        pos+=iso[pos]
    assert iso[pos+33:pos+33+iso[pos+32]]==b"LINDA.MIC;1"
    output.mkdir(exist_ok=True)
    target=output/(NAME+".bin")
    with target.open("wb") as f:
        f.write(src)
        for lba,blob in [(16,pvd),(23,iso)]:
            f.seek(lba*2352)
            f.write(doctor.sector(lba,blob,src[lba*2352+16:lba*2352+20]))
        f.seek(len(src))
        for k in range(0,len(mic),2048):
            f.write(doctor.sector(start+k//2048,mic[k:k+2048],b"\0\0\x08\0"))
    (output/(NAME+".cue")).write_text(f'FILE "{NAME}.bin" BINARY\n  TRACK 01 MODE2/2352\n    INDEX 01 00:00:00\n')
    report={"draft_sha256":hashlib.sha256(DRAFT.read_bytes()).hexdigest(),"changed_banks":report,"matched_entries":names,
        "preserved": ["PS1 doctor scene text (slot 71; event added by build.py)", "PS1 tree inspection/engraving", "PS1 oldster wording (582@0x137F)"],
        "not_ported": {"184@0x67CE": "Saturn-only singing action; PS1 trigger not implemented", "695@0x81FC": "Saturn Kokubu challenge introduction; challenge mode not ported"}}
    print(len(report["changed_banks"]),"banks rebuilt",flush=True)
    return target, report

if __name__=="__main__":
    if len(sys.argv)!=3:
        sys.exit("Usage: python dialogue.py original.bin output-directory")
    build(Path(sys.argv[1]),Path(sys.argv[2]))
