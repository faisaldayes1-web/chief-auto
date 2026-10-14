"""Synthesizes Chief Auto's sound effects and music loops (numpy only), then encodes them to Ogg Vorbis
with ffmpeg into assets/audio/. Everything is generated here, so there are no third-party licences.

    python3 tools/audio_synth.py [out_dir]      # default assets/audio
"""
import os
import subprocess
import sys
import wave

import numpy as np

SR = 44100
rng = np.random.default_rng(7)


def t_(dur):
    return np.arange(int(SR * dur)) / SR


def env_adsr(n, a=0.005, d=0.1, s=0.6, r=0.2, sus_len=None):
    a_n, d_n, r_n = int(a * SR), int(d * SR), int(r * SR)
    s_n = max(0, n - a_n - d_n - r_n) if sus_len is None else int(sus_len * SR)
    e = np.concatenate([np.linspace(0, 1, a_n, endpoint=False), np.linspace(1, s, d_n, endpoint=False),
                        np.full(s_n, s), np.linspace(s, 0, r_n)])
    return np.pad(e, (0, max(0, n - len(e))))[:n]


def exp_dec(n, tau):
    return np.exp(-np.arange(n) / (tau * SR))


def note_hz(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def lp_fast(x, cutoff):
    # FFT brick-ish low-pass with a soft knee, for long buffers
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / SR)
    X *= 1 / (1 + (f / cutoff) ** 4)
    return np.fft.irfft(X, len(x))


def hp_fast(x, cutoff):
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / SR)
    X *= 1 - 1 / (1 + (f / cutoff) ** 4)
    return np.fft.irfft(X, len(x))


def epiano(hz, dur, vel=1.0):
    """FM electric piano: bell-ish attack that mellows."""
    t = t_(dur)
    n = len(t)
    mod_idx = 2.2 * exp_dec(n, 0.25) + 0.3
    y = np.sin(2 * np.pi * hz * t + mod_idx * np.sin(2 * np.pi * hz * t))
    y += 0.25 * np.sin(2 * np.pi * 2 * hz * t) * exp_dec(n, 0.4)
    return y * exp_dec(n, 1.2) * env_adsr(n, 0.004, 0.05, 1.0, 0.08) * vel


def soft_bass(hz, dur):
    t = t_(dur)
    n = len(t)
    y = np.sin(2 * np.pi * hz * t) + 0.3 * np.sin(2 * np.pi * 2 * hz * t) * exp_dec(n, 0.15)
    return y * env_adsr(n, 0.01, 0.15, 0.7, 0.12)


def kick(dur=0.35):
    t = t_(dur)
    f = 45 + 90 * np.exp(-t / 0.04)
    ph = 2 * np.pi * np.cumsum(f) / SR
    return np.sin(ph) * exp_dec(len(t), 0.12)


def snare(dur=0.25):
    n = int(SR * dur)
    noise = hp_fast(rng.standard_normal(n), 1500) * exp_dec(n, 0.06)
    body = np.sin(2 * np.pi * 185 * t_(dur)) * exp_dec(n, 0.04)
    return 0.6 * noise + 0.5 * body


def hat(dur=0.06, open_=False):
    n = int(SR * (0.25 if open_ else dur))
    return hp_fast(rng.standard_normal(n), 7000) * exp_dec(n, 0.08 if open_ else 0.015)


def place(buf, x, at, gain=1.0):
    i = int(at * SR)
    j = min(len(buf), i + len(x))
    if i < len(buf):
        buf[i:j] += x[: j - i] * gain


def write(path, data):
    data = np.asarray(data, dtype=np.float64)
    if data.ndim == 1:
        data = np.stack([data, data], axis=1)
    peak = np.max(np.abs(data)) or 1.0
    data = data / peak * 0.89
    pcm = (data * 32767).astype(np.int16)
    wav = path + ".wav"
    with wave.open(wav, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", wav, "-c:a", "libvorbis", "-q:a", "4", path + ".ogg"],
                   check=True)
    os.remove(wav)


# ------------------------------------------------------------------ music

def music_loop(chords, bpm, bars_per_chord, swing=0.0, drums=True, keys_rhythm=(0, 1.5, 2.5), cutoff=5200,
               bass_pattern=(0, 2.5), melody=None):
    beat = 60.0 / bpm
    bar = 4 * beat
    total = len(chords) * bars_per_chord * bar
    n = int(total * SR)
    tail = int(2.0 * SR)   # room for ringing notes; wrapped onto the start so the loop is seamless
    n_all = n + tail
    keys = np.zeros(n_all)
    bass = np.zeros(n_all)
    drm = np.zeros(n_all)
    mel = np.zeros(n_all)
    for ci, ch in enumerate(chords):
        for b in range(bars_per_chord):
            t0 = (ci * bars_per_chord + b) * bar
            for k, pos in enumerate(keys_rhythm):
                dur = (keys_rhythm[k + 1] - pos) * beat if k + 1 < len(keys_rhythm) else (4 - pos) * beat
                for m in ch[1:]:
                    place(keys, epiano(note_hz(m), dur + 0.4, 0.55 + 0.1 * rng.random()), t0 + pos * beat
                          + rng.random() * 0.012, 0.32)
            for pos in bass_pattern:
                place(bass, soft_bass(note_hz(ch[0]), beat * 1.4), t0 + pos * beat, 0.9)
            if drums:
                for q in range(8):
                    at = t0 + q * beat / 2 + (swing * beat / 2 if q % 2 else 0)
                    place(drm, hat(open_=(q == 7 and b % 2 == 1)), at, 0.16 if q % 2 else 0.24)
                place(drm, kick(), t0, 0.9)
                place(drm, kick(), t0 + 2.5 * beat, 0.7)
                place(drm, snare(), t0 + beat, 0.42)
                place(drm, snare(), t0 + 3 * beat, 0.42)
    if melody:
        for (bar_i, pos, m, ln) in melody:
            place(mel, epiano(note_hz(m), ln * beat + 0.5, 0.8), bar_i * bar + pos * beat, 0.3)
    keys = lp_fast(keys, cutoff)
    mel = lp_fast(mel, cutoff + 1500)
    # stereo: keys a little wide (Haas), bass and drums centre
    d = int(0.011 * SR)
    kl = keys
    kr = np.concatenate([np.zeros(d), keys[:-d]])
    ml = np.concatenate([np.zeros(d // 2), mel[: -(d // 2)]])
    left = kl + bass * 0.8 + drm + ml
    right = kr + bass * 0.8 + drm * 0.95 + mel
    out = np.stack([left, right], axis=1)
    out[:tail] += out[n:]
    out = out[:n]
    # gentle vinyl hiss + room
    hiss = lp_fast(rng.standard_normal(n), 6000) * 0.004
    out += hiss[:, None]
    return out


def main(out):
    os.makedirs(out, exist_ok=True)
    C = 48
    # "Showroom" daytime: smooth Cmaj9 - Am9 - Dm9 - G13, 92 bpm, light swing
    day = [[C - 12, 64, 67, 71, 74], [C - 15, 60, 64, 67, 71], [C - 10, 60, 65, 69, 72], [C - 17, 59, 62, 65, 69]]
    mel = []
    phrase = [(0, 0, 76, 1.5), (0, 1.5, 74, 0.5), (0, 2, 72, 1), (0, 3, 71, 1),
              (1, 0, 72, 2), (1, 2.5, 69, 1.5), (2, 0, 69, 1), (2, 1, 72, 1), (2, 2, 74, 2),
              (3, 0, 71, 1.5), (3, 1.5, 67, 0.5), (3, 2, 69, 2)]
    for rep in (1, 3):
        for (b, p, m, ln) in phrase:
            mel.append((rep * 4 + b, p, m, ln))
    write(os.path.join(out, "music_day"), music_loop(day * 4, 92, 1, swing=0.18, melody=mel))
    # "Office" auctions/desk: brighter, more pulse, 104 bpm
    office = [[C - 7, 65, 69, 72, 76], [C - 5, 67, 71, 74, 77], [C - 15, 64, 67, 72, 76], [C - 10, 65, 69, 72, 74]]
    write(os.path.join(out, "music_office"),
          music_loop(office * 4, 104, 1, swing=0.1, keys_rhythm=(0, 0.75, 1.5, 2.5, 3.25), cutoff=6000,
                     bass_pattern=(0, 1.5, 2.5, 3.5)))
    # "Night" title/home/closing: slow, no drums, Fmaj7 - Em7 - Dm7 - Cmaj7
    night = [[C - 7, 64, 69, 72, 76], [C - 8, 62, 67, 71, 74], [C - 10, 60, 65, 69, 72], [C - 12, 59, 64, 67, 71]]
    write(os.path.join(out, "music_night"),
          music_loop(night * 2, 70, 2, drums=False, keys_rhythm=(0, 2), cutoff=3800, bass_pattern=(0,)))

    # ------------------------------------------------------------------ effects
    def sfx(name, x):
        write(os.path.join(out, name), x)

    # UI click: short soft tick
    n = int(0.05 * SR)
    sfx("click", lp_fast(rng.standard_normal(n), 3500) * exp_dec(n, 0.006)
        + 0.6 * np.sin(2 * np.pi * 1800 * t_(0.05)) * exp_dec(n, 0.008))
    # hover: very quiet higher tick
    n = int(0.03 * SR)
    sfx("hover", np.sin(2 * np.pi * 2600 * t_(0.03)) * exp_dec(n, 0.005))
    # cash register "cha-ching": drawer clunk + two bells
    d = 0.9
    buf = np.zeros(int(d * SR))
    place(buf, lp_fast(rng.standard_normal(int(0.08 * SR)), 900) * exp_dec(int(0.08 * SR), 0.02), 0, 1.2)
    for at, hz in ((0.09, 2093), (0.2, 2637)):
        tt = t_(0.7)
        bell = (np.sin(2 * np.pi * hz * tt) + 0.5 * np.sin(2 * np.pi * hz * 2.76 * tt) * exp_dec(len(tt), 0.08)
                + 0.3 * np.sin(2 * np.pi * hz * 5.4 * tt) * exp_dec(len(tt), 0.03)) * exp_dec(len(tt), 0.25)
        place(buf, bell, at, 0.5)
    sfx("cash", buf)
    # success chime: rising major arpeggio
    buf = np.zeros(int(1.0 * SR))
    for i, m in enumerate((72, 76, 79, 84)):
        place(buf, epiano(note_hz(m), 0.7, 1.0), i * 0.07, 0.6)
    sfx("success", buf)
    # error / no: two low soft blips
    buf = np.zeros(int(0.4 * SR))
    for i, m in enumerate((55, 51)):
        tt = t_(0.14)
        place(buf, np.sin(2 * np.pi * note_hz(m) * tt) * env_adsr(len(tt), 0.005, 0.03, 0.7, 0.05), i * 0.13, 0.8)
    sfx("error", buf)
    # notification: two-tone ding
    buf = np.zeros(int(0.8 * SR))
    place(buf, epiano(note_hz(81), 0.6), 0, 0.7)
    place(buf, epiano(note_hz(76), 0.6), 0.12, 0.7)
    sfx("notify", buf)
    # door chime (a customer walks in): classic ding-dong
    buf = np.zeros(int(1.6 * SR))
    for at, m in ((0, 76), (0.45, 72)):
        tt = t_(1.1)
        hz = note_hz(m)
        bell = (np.sin(2 * np.pi * hz * tt) + 0.35 * np.sin(2 * np.pi * hz * 3.0 * tt) * exp_dec(len(tt), 0.1))
        place(buf, bell * exp_dec(len(tt), 0.45), at, 0.6)
    sfx("door", buf)
    # auction gavel / bid: wooden knock
    n = int(0.15 * SR)
    knock = (np.sin(2 * np.pi * 420 * t_(0.15)) * exp_dec(n, 0.02) + 0.6 * np.sin(2 * np.pi * 980 * t_(0.15))
             * exp_dec(n, 0.01) + lp_fast(rng.standard_normal(n), 2500) * exp_dec(n, 0.006) * 0.8)
    sfx("bid", knock)
    buf = np.zeros(int(0.5 * SR))
    place(buf, knock, 0, 1)
    place(buf, knock, 0.16, 1)
    sfx("gavel", buf)
    # pen signature: scratchy filtered noise swishes
    buf = np.zeros(int(0.9 * SR))
    for i in range(5):
        L = 0.08 + 0.06 * rng.random()
        nn = int(L * SR)
        s = hp_fast(rng.standard_normal(nn), 2500) * np.sin(np.linspace(0, np.pi, nn)) ** 2
        place(buf, s, 0.05 + i * 0.15, 0.5)
    sfx("sign", buf)
    # paper shuffle
    nn = int(0.35 * SR)
    sfx("paper", lp_fast(hp_fast(rng.standard_normal(nn), 800), 6000) * np.sin(np.linspace(0, np.pi, nn)) ** 1.5
        * (0.6 + 0.4 * np.sin(np.linspace(0, 18, nn))))
    # wrench / repair: metallic ratchet clicks
    buf = np.zeros(int(0.7 * SR))
    for i in range(6):
        nn = int(0.03 * SR)
        clk = (hp_fast(rng.standard_normal(nn), 3000) * exp_dec(nn, 0.004)
               + 0.5 * np.sin(2 * np.pi * 3400 * t_(0.03)) * exp_dec(nn, 0.006))
        place(buf, clk, i * 0.09, 0.8)
    sfx("wrench", buf)
    # car engine start: starter whirr then idle rumble
    d = 2.4
    tt = t_(d)
    nn = len(tt)
    rpm = np.where(tt < 0.55, 6 + 4 * tt, 0) + np.where(tt >= 0.55, 14 + 26 * np.exp(-(tt - 0.55) / 0.25) + 0.0, 0)
    ph = 2 * np.pi * np.cumsum(rpm) / SR
    firing = np.sin(ph) ** 15 * np.sign(np.sin(ph))
    rumble = lp_fast(firing + 0.3 * lp_fast(rng.standard_normal(nn), 300), 420)
    starter = np.sin(2 * np.pi * 230 * tt + 3 * np.sin(2 * np.pi * 9 * tt)) * (tt < 0.6) * 0.25
    ev = np.clip(tt / 0.05, 0, 1) * np.clip((d - tt) / 0.5, 0, 1)
    sfx("engine", (rumble * (tt >= 0.5) * 1.6 + starter) * ev)
    # level up: bright fanfare
    buf = np.zeros(int(1.6 * SR))
    for i, m in enumerate((67, 72, 76, 79)):
        place(buf, epiano(note_hz(m), 0.5), i * 0.09, 0.5)
    for m in (72, 76, 79, 84):
        place(buf, epiano(note_hz(m), 1.2), 0.42, 0.35)
    sfx("levelup", buf)
    # coin: small single bell
    tt = t_(0.4)
    sfx("coin", (np.sin(2 * np.pi * 1975 * tt) + 0.4 * np.sin(2 * np.pi * 2637 * tt)) * exp_dec(len(tt), 0.09))
    # whoosh: page/screen change
    nn = int(0.3 * SR)
    w = rng.standard_normal(nn)
    w = lp_fast(w, 1800) * np.sin(np.linspace(0, np.pi, nn)) ** 2
    sfx("whoosh", w)
    # lot ambience: distant traffic + gulls-ish chirps + breeze, 20 s loop
    d = 20.0
    nn = int(d * SR)
    breeze = lp_fast(rng.standard_normal(nn), 500) * (0.6 + 0.4 * np.sin(np.linspace(0, 2 * np.pi * 3, nn)))
    traffic = np.zeros(nn)
    for k in range(5):
        at = rng.random() * (d - 4)
        L = 3.5
        m = int(L * SR)
        car = lp_fast(rng.standard_normal(m), 260) * np.sin(np.linspace(0, np.pi, m)) ** 2
        place(traffic, car, at, 1.6)
    birds = np.zeros(nn)
    for k in range(4):
        at = rng.random() * (d - 1)
        tt = t_(0.18)
        f = 2400 + 900 * np.sin(np.linspace(0, np.pi, len(tt)))
        ch = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.sin(np.linspace(0, np.pi, len(tt)))
        place(birds, ch, at, 0.08)
        place(birds, ch, at + 0.22, 0.06)
    amb = breeze * 0.5 + traffic + birds
    fade = int(1.0 * SR)   # crossfade the ends so the loop is seamless
    amb[:fade] = amb[:fade] * np.linspace(0, 1, fade) + amb[-fade:] * np.linspace(1, 0, fade)
    amb = amb[:-fade]
    write(os.path.join(out, "amb_lot"), amb)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "..", "assets", "audio"))
