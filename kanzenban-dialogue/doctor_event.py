"""Playing-doctor event for MIC slot 71 (Scenario A, Joint Playroom), plus
shared binary and CD-sector helpers. Target: v0.95.9 English PROG.BIN."""
import struct
import hashlib

def u16(b, off): return struct.unpack_from('<H', b, off)[0]
def u32(b, off): return struct.unpack_from('<I', b, off)[0]
def word(n): return struct.pack('<H', n)
def sha(b): return hashlib.sha256(b).hexdigest()

def program(stock):
    assert sha(stock) == '8ba351bbd3f3730ce4d598909260a79293d38f840c8d55a630e4396c2e07ef8c'
    bank = bytearray(stock[:0xa70])
    records = stock[0xb06:0xf70].split(b'\0')[:-1]
    assert len(records) == 0x16
    # Each line break and wait is explicit in the PS1 renderer.
    records[0x0b] = (b'\x0c"First, please take off your...\rsomething." Remember that, Ken?\x12\r'
                     b'\x0cYou said it with the straightest\rface. The voice you put on, though!\rYou sounded like such a perv.\x12\r'
                     b'\x0cSo... what did I take off first?')
    # Pad the top cells so the selectable columns cover the wider lower labels.
    records[0x0c] = b'\r\x01Bra            \x0e / \x01Camisole   \x0e\r\x01Flare pants\x0e / \x01Panties\x0e'
    bullet = b'\x01\x81\x9e\x0e'
    # Condensed wording to fit each selectable row beside Ken's portrait.
    records[0x0f] = b'\x0c' + b'\r'.join(bullet+x for x in
        (b"I'll really undress you!", b'Fine. Take off your \x1d first.', b'Yeah. Saw that coming.'))
    garment_base = len(records)
    records.extend((b'bra', b'camisole', b'flare pants', b'panties'))
    invitation = len(records)
    records.append(b"\x0cOh! Ken, I think I remember!\rCome on, let's try it. Say it again,\rjust like you did back then.\x12")
    ken = len(records)
    records.append(b'\x0cFirst... please take off your\r\x1d.\x12')
    lookup = len(bank)
    # This is the switch/substitution idiom from the bank's original scent routine at 0805.
    table = lookup + 3 + 4*3
    bank += b'\xa2' + word(table)
    for i in range(4):
        bank += bytes([0x3b, garment_base+i, 0xa0])
    bank += b'\x04' + word(lookup+3)
    for i in range(4): bank += word(i) + word(lookup+3+3*i)

    first = len(bank)
    bank += bytes([0xa3, invitation])
    bank += stock[0x571:0x57a]             # close Linda
    face = bytearray(stock[0x533:0x559])  # left portrait with matching text margin
    face[4:6] = word(0x336)              # kao_k1.obj; checked against inline resource below
    assert stock[0x336:0x336+2] == bytes([0x35, 0x0a])
    # Reuse the complete left portrait setup, including its text inset.

    bank += face
    bank += bytes.fromhex('90 c2 32 d5 f8 00 b2') + word(lookup)
    bank += bytes([0xa3, ken, 0xa1]) + word(0x571)
    second = len(bank)
    # Saturn's (first choice + rand(3) + 1) & 3. Refill the PS1 substitution queue.
    bank += bytes.fromhex('90 c2 32 d5 f8 00 ff 93 2f e6 ff 91 e6 ff 93 eb b2') + word(lookup)
    bank += stock[0x6f1:0x6f6] + b'\xa1' + word(0x6f6)
    bank[0x563:0x571] = bytes.fromhex('a3 0b 3a a3 0c 90 1c 01 c5 f8 00 a1') + word(first)
    bank[0x6f1:0x6f4] = b'\xa1' + word(second)
    object_start = len(bank)
    bank += stock[0xa70:0xb06]
    dialogue_start = len(bank)
    bank += b'\0'.join(records) + b'\0'
    skill_start = len(bank)
    bank += stock[0xf70:]
    for at, ptr in zip(range(0x14,0x20,2), [object_start]*4+[dialogue_start, skill_start]):
        bank[at:at+2] = word(ptr)
    return bytes(bank)

def rebuild(archive):
    def offset(pos): return int.from_bytes(archive[pos+13:pos+16], 'little')
    first, second = offset(0), offset(16)
    directory = bytearray(archive[:first])
    new = program(archive[first:second])
    # Preserve alignment of every following resource relative to the original allocation.
    new += bytes((second-first-len(new))%4)
    delta = len(new) - (second-first)
    for pos in range(16,first,16):
        directory[pos+13:pos+16] = (offset(pos) + delta).to_bytes(3,'little')
    end = offset(first-16)
    assert not any(archive[end:])
    result = directory + new + archive[second:end]
    result += bytes((-len(result))%2048)
    return result

def tables():
    edc, forward, back = [], [], [0]*256
    for i in range(256):
        n = i
        for _ in range(8): n = (n >> 1) ^ (0xd8018001 if n&1 else 0)
        edc.append(n)
        n = (i << 1) ^ (0x11d if i & 128 else 0)
        forward.append(n)
        back[i ^ n] = i
    return edc, forward, back
EDC, F, B = tables()

def parity(src, major_count, minor_count, major_mult, minor_inc):
    out = bytearray(major_count*2)
    size = major_count*minor_count
    for major in range(major_count):
        index = (major>>1)*major_mult + (major&1)
        a = b = 0
        for _ in range(minor_count):
            v = src[index]
            index = (index+minor_inc)%size
            a, b = F[a^v], b^v
        a = B[F[a]^b]
        out[major],out[major+major_count] = a,a^b
    return out

def bcd(n): return n//10*16+n%10
def sector(lba, data, sub):
    assert len(data) == 2048 and len(sub) == 4 and not sub[2]&32
    raw = bytearray(2352)
    raw[:12] = b'\0'+b'\xff'*10+b'\0'
    raw[16:24] = sub*2
    raw[24:2072] = data
    c = 0
    for v in raw[16:2072]: c = (c>>8)^EDC[(c^v)&255]
    struct.pack_into('<I',raw,2072,c)
    raw[2076:2248] = parity(raw[12:2076],86,24,2,86)
    raw[2248:] = parity(raw[12:2248],52,43,86,88)
    msf = lba+150
    raw[12:16] = bytes((bcd(msf//4500),bcd((msf//75)%60),bcd(msf%75),2))
    return raw

def checkword(archive):
    return sum(x[0] for x in struct.iter_unpack('<I',archive)) & 0xffffffff
