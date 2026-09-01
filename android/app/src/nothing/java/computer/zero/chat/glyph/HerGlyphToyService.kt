package computer.zero.chat.glyph

import android.app.Service
import android.content.ComponentName
import android.content.Intent
import android.os.Bundle
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.os.Message
import android.os.Messenger
import com.nothing.ketchum.Glyph
import com.nothing.ketchum.GlyphMatrixManager
import com.nothing.ketchum.GlyphToy
import computer.zero.chat.api.HerClient
import computer.zero.chat.api.HerSnapshot
import computer.zero.chat.her.HerGlyphArt
import computer.zero.chat.her.HerPrefs
import computer.zero.chat.her.HerVoiceActivity
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

/**
 * Her as a Glyph Toy on the Nothing Phone (3) — the 25x25 Glyph Matrix on
 * the back. Built against the Glyph Matrix Developer Kit
 * (github.com/Nothing-Developer-Programme/GlyphMatrix-Developer-Kit):
 * GlyphMatrixManager.init/register/setMatrixFrame, and the toy events
 * EVENT_CHANGE (long press on the Glyph button) and EVENT_AOD (once a minute
 * on the always-on display).
 *
 * What it shows is Her's presence, nothing else: quiet ring, a travelling
 * dot while she thinks, a "?" when she has a question, a filled centre only
 * when a human-set presence level (ambient/live) says something is there.
 * Long press = talk to her (HerVoiceActivity). This flavor only builds when
 * app/libs/glyph-matrix-sdk-2.0.aar is present (see build.gradle.kts).
 */
class HerGlyphToyService : Service() {
    private var gm: GlyphMatrixManager? = null
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main)
    private var loop: Job? = null
    private var snapshot: HerSnapshot? = null
    private var reachable = false

    private val handler = object : Handler(Looper.getMainLooper()) {
        override fun handleMessage(msg: Message) {
            if (msg.what != GlyphToy.MSG_GLYPH_TOY) return
            when (msg.data.getString(GlyphToy.MSG_GLYPH_TOY_DATA)) {
                GlyphToy.EVENT_CHANGE -> startActivity(
                    Intent(this@HerGlyphToyService, HerVoiceActivity::class.java)
                        .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
                )
                GlyphToy.EVENT_AOD -> scope.launch { refresh(); render(0f) }
            }
        }
    }
    private val messenger = Messenger(handler)

    override fun onBind(intent: Intent?): IBinder {
        val m = GlyphMatrixManager.getInstance(applicationContext)
        gm = m
        m.init(object : GlyphMatrixManager.Callback {
            override fun onServiceConnected(name: ComponentName?) {
                m.register(Glyph.DEVICE_23112)
                startLoop()
            }
            override fun onServiceDisconnected(name: ComponentName?) {}
        })
        return messenger.binder
    }

    override fun onUnbind(intent: Intent?): Boolean {
        loop?.cancel(); scope.cancel()
        gm?.unInit(); gm = null
        return false
    }

    private fun startLoop() {
        loop?.cancel()
        loop = scope.launch {
            var tick = 0
            while (isActive) {
                if (tick % 40 == 0) refresh()           // every ~5s
                render((tick % 40) / 40f)               // breathing/travel phase
                tick++
                delay(125)
            }
        }
    }

    private suspend fun refresh() {
        val prefs = HerPrefs(this)
        if (!prefs.paired) { reachable = false; snapshot = null; return }
        HerClient(prefs.baseUrl, prefs.token).presence()
            .onSuccess { snapshot = it; reachable = true }
            .onFailure { reachable = false }
    }

    private fun render(phase: Float) {
        val s = snapshot
        val state = when {
            !reachable || s == null || !s.alive -> "asleep"
            else -> s.status
        }
        val p = s?.presence
        gm?.setMatrixFrame(HerGlyphArt.frame(state, p?.question != null, p?.attention == true, phase))
    }
}
