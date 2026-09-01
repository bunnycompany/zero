package computer.zero.chat.her

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Bundle
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.speech.tts.TextToSpeech
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import computer.zero.chat.api.HerClient
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.launch
import androidx.lifecycle.lifecycleScope
import java.util.Locale

/**
 * The voice path — and the glasses path. Ray-Ban Meta (any generation) reach
 * a phone app as a Bluetooth headset: their mics are this phone's mic and
 * their speakers are this phone's audio route. So "talk to Her through the
 * glasses" is: listen with SpeechRecognizer, send to the bridge, speak the
 * answer with TextToSpeech. No Meta SDK needed for that; the Ray-Ban
 * Display's in-lens page is her/glasses/index.html, served by the bridge.
 *
 * Reached by: long-pressing Her's Glyph toy (Nothing Phone 3), or setting
 * this app as the assist app (ACTION_ASSIST in the manifest).
 */
class HerVoiceActivity : ComponentActivity() {
    private val status = MutableStateFlow("Listening…")
    private var tts: TextToSpeech? = null
    private var recognizer: SpeechRecognizer? = null

    private val askMic = registerForActivityResult(ActivityResultContracts.RequestPermission()) { ok ->
        if (ok) listen() else finishWith("I need the microphone to hear you.")
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            MaterialTheme {
                Surface(color = MaterialTheme.colorScheme.background) {
                    val s by status.collectAsState()
                    Box(Modifier.fillMaxSize().padding(32.dp), contentAlignment = Alignment.Center) {
                        Text(s, style = MaterialTheme.typography.headlineSmall)
                    }
                }
            }
        }
        tts = TextToSpeech(this) { if (it == TextToSpeech.SUCCESS) tts?.language = Locale.getDefault() }
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED)
            listen() else askMic.launch(Manifest.permission.RECORD_AUDIO)
    }

    private fun listen() {
        if (!SpeechRecognizer.isRecognitionAvailable(this)) return finishWith("No speech recognition on this phone.")
        val r = SpeechRecognizer.createSpeechRecognizer(this)
        recognizer = r
        r.setRecognitionListener(object : RecognitionListener {
            override fun onResults(results: Bundle?) {
                val text = results?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)?.firstOrNull()
                if (text.isNullOrBlank()) finishWith("I didn't catch that.") else send(text)
            }
            override fun onError(error: Int) { finishWith("I didn't catch that.") }
            override fun onReadyForSpeech(params: Bundle?) {}
            override fun onBeginningOfSpeech() {}
            override fun onRmsChanged(rmsdB: Float) {}
            override fun onBufferReceived(buffer: ByteArray?) {}
            override fun onEndOfSpeech() { status.value = "…" }
            override fun onPartialResults(partialResults: Bundle?) {}
            override fun onEvent(eventType: Int, params: Bundle?) {}
        })
        r.startListening(Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
        })
    }

    private fun send(text: String) {
        val prefs = HerPrefs(this)
        if (!prefs.paired) return finishWith("Pair this phone with your Mac first.")
        status.value = "You: $text"
        val client = HerClient(prefs.baseUrl, prefs.token)
        lifecycleScope.launch {
            val snap = client.presence().getOrNull()
            val replyTo = snap?.presence?.question?.id  // spoken words answer her open question, if any
            val sentAt = System.currentTimeMillis() / 1000.0
            client.say(text, replyTo).onFailure { return@launch finishWith("Can't reach your Mac right now.") }
            repeat(60) {
                delay(1500)
                val s = client.presence().getOrNull()
                if (s != null && (s.answerTs ?: 0.0) > sentAt) {
                    val answer = s.answer?.text ?: ""
                    return@launch finishWith(answer, speak = true)
                }
            }
            finishWith("Still thinking — the answer will be waiting on the Mac.", speak = true)
        }
    }

    private fun finishWith(text: String, speak: Boolean = false) {
        status.value = text
        if (speak) {
            tts?.speak(text, TextToSpeech.QUEUE_FLUSH, null, "her")
            lifecycleScope.launch { delay(minOf(12000L, 2000L + text.length * 60L)); finish() }
        } else {
            lifecycleScope.launch { delay(2500); finish() }
        }
    }

    override fun onDestroy() {
        recognizer?.destroy(); tts?.shutdown()
        super.onDestroy()
    }
}
