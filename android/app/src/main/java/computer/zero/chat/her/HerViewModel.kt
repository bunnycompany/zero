package computer.zero.chat.her

import android.app.Application
import android.os.Build
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import computer.zero.chat.api.HerClient
import computer.zero.chat.api.HerSnapshot
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

data class HerUiState(
    val baseUrl: String = "",
    val paired: Boolean = false,
    val snapshot: HerSnapshot? = null,
    val error: String? = null,
    val busy: Boolean = false,
    // what you last said and whether her reply has landed since
    val pendingSince: Double? = null,
)

/** Her on the phone. Settings live in the same prefs the Glyph toy service
 *  reads (HerPrefs), so the back of the phone and the front agree. */
class HerViewModel(app: Application) : AndroidViewModel(app) {
    private val prefs = HerPrefs(app)
    private val _state = MutableStateFlow(
        HerUiState(baseUrl = prefs.baseUrl, paired = prefs.token != null)
    )
    val state: StateFlow<HerUiState> = _state.asStateFlow()
    private var pollJob: Job? = null

    init { startPolling() }

    private fun client() = HerClient(_state.value.baseUrl, prefs.token)

    fun setBaseUrl(url: String) {
        prefs.baseUrl = url.trim()
        _state.value = _state.value.copy(baseUrl = url.trim(), error = null)
    }

    fun pair(code: String) {
        val name = "${Build.MANUFACTURER} ${Build.MODEL}".trim()
        _state.value = _state.value.copy(busy = true, error = null)
        viewModelScope.launch {
            client().pair(code, name).onSuccess {
                prefs.token = it.token
                prefs.deviceId = it.device
                _state.value = _state.value.copy(paired = true, busy = false)
                refresh()
            }.onFailure {
                _state.value = _state.value.copy(busy = false, error = it.message ?: "couldn't pair")
            }
        }
    }

    fun unpair() {
        prefs.token = null; prefs.deviceId = null
        _state.value = _state.value.copy(paired = false, snapshot = null)
    }

    fun refresh() {
        if (!_state.value.paired) return
        viewModelScope.launch {
            client().presence().onSuccess { snap ->
                val pending = _state.value.pendingSince
                val landed = pending != null && (snap.answerTs ?: 0.0) > pending
                _state.value = _state.value.copy(
                    snapshot = snap, error = null,
                    pendingSince = if (landed) null else pending,
                )
            }.onFailure {
                // offline is a promise, not an error: what you typed waits on the Mac
                _state.value = _state.value.copy(error = "Can't reach your Mac right now — ${it.message}")
            }
        }
    }

    /** Send text. If Her has a question open and [answerHer] is true, the
     *  text is tagged as that answer; otherwise it is an ordinary ask. */
    fun say(text: String, answerHer: Boolean) {
        val t = text.trim()
        if (t.isEmpty() || _state.value.busy) return
        val q = _state.value.snapshot?.presence?.question
        val replyTo = if (answerHer) q?.id else null
        _state.value = _state.value.copy(busy = true, error = null)
        viewModelScope.launch {
            client().say(t, replyTo).onSuccess {
                _state.value = _state.value.copy(
                    busy = false, pendingSince = System.currentTimeMillis() / 1000.0,
                )
            }.onFailure {
                _state.value = _state.value.copy(busy = false, error = it.message ?: "couldn't send")
            }
        }
    }

    private fun startPolling() {
        pollJob?.cancel()
        pollJob = viewModelScope.launch {
            while (isActive) {
                refresh()
                delay(if (_state.value.pendingSince != null) 1500 else 5000)
            }
        }
    }
}
