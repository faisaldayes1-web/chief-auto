extends Node
## Sound (autoload "Sfx"): one-shot effects, a music track per area with crossfades, and lot ambience.
## Every sound is synthesized by tools/audio_synth.py into res://assets/audio/<name>.ogg.

const DIR := "res://assets/audio/%s.ogg"
## per-effect level in dB, so the effects sit together under the music
const GAIN := {"click": -10.0, "hover": -22.0, "cash": -4.0, "success": -6.0, "error": -8.0, "notify": -9.0,
	"door": -10.0, "bid": -8.0, "gavel": -4.0, "sign": -6.0, "paper": -8.0, "wrench": 2.0, "engine": -4.0,
	"levelup": -4.0, "coin": -10.0, "whoosh": -14.0}
## which music fits each screen; screens not listed keep whatever is playing
const SCREEN_MUSIC := {"title": "music_night", "home": "music_night", "lot": "music_day", "showroom": "music_day",
	"garage": "music_day", "staff": "music_day", "marco": "music_day", "pc": "music_office", "office": "music_office"}

var _pool: Array[AudioStreamPlayer] = []
var _streams := {}
var _music_a: AudioStreamPlayer
var _music_b: AudioStreamPlayer
var _music_name := ""
var _amb: AudioStreamPlayer
var _last_play := {}


func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	for i in 8:
		var p := AudioStreamPlayer.new()
		p.bus = "SFX"
		add_child(p)
		_pool.append(p)
	_music_a = _music_player()
	_music_b = _music_player()
	_amb = AudioStreamPlayer.new()
	_amb.bus = "SFX"
	_amb.volume_db = -20.0
	add_child(_amb)
	# every button in the game clicks
	get_tree().node_added.connect(func(n: Node):
		if n is BaseButton and not n.has_meta("silent"):
			(n as BaseButton).pressed.connect(play.bind("click", 0.04)))


func _music_player() -> AudioStreamPlayer:
	var p := AudioStreamPlayer.new()
	p.bus = "Music"
	p.volume_db = -80.0
	add_child(p)
	return p


func _stream(name: String, loop := false) -> AudioStream:
	if _streams.has(name):
		return _streams[name]
	var path := DIR % name
	var s: AudioStream = load(path) if ResourceLoader.exists(path) else null
	if s is AudioStreamOggVorbis:
		(s as AudioStreamOggVorbis).loop = loop
	_streams[name] = s
	return s


## Plays a one-shot effect. The same effect is not restarted within 40 ms (button storms).
func play(name: String, pitch_jitter := 0.0) -> void:
	if _pool.is_empty():
		return   # not in the tree yet (tests that load scripts directly)
	var now := Time.get_ticks_msec()
	if now - int(_last_play.get(name, -1000)) < 40:
		return
	_last_play[name] = now
	var s := _stream(name)
	if s == null:
		return
	var p: AudioStreamPlayer = null
	for q in _pool:
		if not q.playing:
			p = q
			break
	if p == null:
		p = _pool[0]
	p.stream = s
	p.volume_db = GAIN.get(name, -8.0)
	p.pitch_scale = 1.0 + randf_range(-pitch_jitter, pitch_jitter)
	p.play()


## Switches the background music for a screen, crossfading over a second.
func screen(name: String) -> void:
	if SCREEN_MUSIC.has(name):
		music(SCREEN_MUSIC[name])
	if name == "lot":
		ambience("amb_lot")
	elif name != "":
		ambience("")


func music(track: String) -> void:
	if track == _music_name:
		return
	_music_name = track
	var old := _music_a
	var nxt := _music_b
	_music_a = nxt   # _music_a is always the current track's player
	_music_b = old
	if old.playing:
		var tw := create_tween()
		tw.tween_property(old, "volume_db", -80.0, 1.2)
		tw.tween_callback(old.stop)
	var s := _stream(track, true)
	if s:
		nxt.stream = s
		nxt.volume_db = -40.0
		nxt.play()
		create_tween().tween_property(nxt, "volume_db", -6.0, 1.2)


func ambience(track: String) -> void:
	if track == "":
		if _amb.playing:
			create_tween().tween_property(_amb, "volume_db", -60.0, 0.8).finished.connect(_amb.stop)
		return
	var s := _stream(track, true)
	if s == null or (_amb.playing and _amb.stream == s and _amb.volume_db > -30.0):
		return
	_amb.stream = s
	_amb.volume_db = -50.0
	_amb.play()
	create_tween().tween_property(_amb, "volume_db", -20.0, 1.0)
