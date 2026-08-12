package computer.zero.chat

import android.app.Application
import android.os.Build
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import computer.zero.chat.api.ChatMessage
import computer.zero.chat.api.OpenAiClient
import computer.zero.chat.api.StreamEvent
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import java.util.UUID

@Serializable
data class UiMessage(
    val role: String,
    val content: String,
    val failed: Boolean = false,
    // live tail of the model's reasoning stream — shown dim while content is
    // empty so a thinking model looks alive instead of stuck
    val thinking: String = "",
)

@Serializable
data class Conversation(
    val id: String,
    val title: String,
    val messages: List<UiMessage> = emptyList(),
)

data class ChatUiState(
    val conversations: List<Conversation> = emptyList(),
    val currentId: String? = null,
    val models: List<String> = emptyList(),
    val selectedModel: String? = null,
    val streaming: Boolean = false,
    val connectionError: String? = null,
    val baseUrl: String = "",
    val apiKey: String = "",
    val temperature: Double = 0.7,
    // composer draft lives here, not in remember{}: fold/unfold recreates the
    // whole composition and half-typed messages must survive it
    val draft: String = "",
) {
    val currentMessages: List<UiMessage>
        get() = conversations.firstOrNull { it.id == currentId }?.messages ?: emptyList()
    val connected: Boolean
        get() = connectionError == null && models.isNotEmpty()
}

private const val MAX_CONVERSATIONS = 50

class ChatViewModel(app: Application) : AndroidViewModel(app) {

    private val prefs = app.getSharedPreferences("zero_chat", Application.MODE_PRIVATE)
    private val json = Json { ignoreUnknownKeys = true }

    private val _state = MutableStateFlow(
        ChatUiState(
            baseUrl = prefs.getString("base_url", defaultBaseUrl()) ?: defaultBaseUrl(),
            apiKey = prefs.getString("api_key", "") ?: "",
            selectedModel = prefs.getString("model", null),
            temperature = prefs.getFloat("temperature", 0.7f).toDouble(),
            conversations = loadConversations(),
        ).let { it.copy(currentId = it.conversations.firstOrNull()?.id) }
    )
    val state: StateFlow<ChatUiState> = _state.asStateFlow()

    private var client = buildClient()
    private var streamJob: Job? = null

    init {
        // once per process, not per composition — fold/rotate must not refetch
        refreshModels()
    }

    fun updateDraft(text: String) {
        _state.value = _state.value.copy(draft = text)
    }

    /** Emulator reaches the host Mac at 10.0.2.2; real devices default to the
     *  project's own inference gateway so a fresh install works anywhere. */
    private fun defaultBaseUrl(): String {
        val emulator = Build.FINGERPRINT.contains("generic") ||
            Build.MODEL.contains("sdk_gphone") ||
            Build.HARDWARE.contains("ranchu")
        return if (emulator) "http://10.0.2.2:8080/v1" else "https://api.danger.plus/v1"
    }

    private fun buildClient() = OpenAiClient(_state.value.baseUrl, _state.value.apiKey)

    private fun loadConversations(): List<Conversation> =
        runCatching {
            json.decodeFromString<List<Conversation>>(prefs.getString("conversations", "[]") ?: "[]")
        }.getOrDefault(emptyList()).map { conv ->
            // a stream that died with the process (crash, swipe-away) must not
            // leave a forever-pending bubble
            conv.copy(messages = conv.messages.map { m ->
                if (m.role == "assistant" && m.content.isEmpty())
                    m.copy(content = "⚠ interrupted — ask again", failed = true)
                else m
            })
        }

    private fun persistConversations(conversations: List<Conversation>) {
        prefs.edit()
            .putString("conversations", json.encodeToString(conversations.take(MAX_CONVERSATIONS)))
            .apply()
    }

    // --- settings -----------------------------------------------------------

    fun updateSettings(baseUrl: String, apiKey: String) {
        prefs.edit().putString("base_url", baseUrl).putString("api_key", apiKey).apply()
        _state.value = _state.value.copy(baseUrl = baseUrl, apiKey = apiKey, connectionError = null)
        client = buildClient()
        refreshModels()
    }

    fun useEmulatorHost() = updateSettings("http://10.0.2.2:8080/v1", _state.value.apiKey)

    fun selectModel(model: String) {
        prefs.edit().putString("model", model).apply()
        _state.value = _state.value.copy(selectedModel = model)
    }

    fun setTemperature(value: Double) {
        prefs.edit().putFloat("temperature", value.toFloat()).apply()
        _state.value = _state.value.copy(temperature = value)
    }

    /** Older gemma-1/2/3 checkpoints stay selectable — the choice is the
     *  user's — but sink below current models so the default stays modern. */
    private fun isOutdated(id: String) =
        Regex("gemma[-_]?[123]\\b", RegexOption.IGNORE_CASE).containsMatchIn(id)

    private fun rankModels(models: List<String>): List<String> =
        models.sortedBy { if (isOutdated(it)) 1 else 0 }

    /** The gateway serves its own "auto" endpoint and does the routing, so on
     *  the gateway we don't rank at all — auto is simply the default. Local
     *  mlx servers have no auto, which is the only place ranking earns its
     *  keep. */
    private fun gatewayAuto() = _state.value.baseUrl.contains("danger.plus")

    fun refreshModels() {
        viewModelScope.launch {
            client.listModels()
                .onSuccess { raw ->
                    val onGateway = gatewayAuto()
                    val models = if (onGateway) listOf("auto") + raw else rankModels(raw)
                    val selected = _state.value.selectedModel?.takeIf { it in models }
                        ?: models.firstOrNull { it == "auto" }
                        ?: models.firstOrNull { "gemma-4" in it }
                        ?: models.firstOrNull { !isOutdated(it) }
                        ?: models.firstOrNull()
                    _state.value = _state.value.copy(
                        models = models, selectedModel = selected, connectionError = null,
                    )
                }
                .onFailure { e ->
                    _state.value = _state.value.copy(
                        connectionError = "Can't reach server: ${e.message}",
                    )
                }
        }
    }

    // --- conversations ------------------------------------------------------

    fun newChat() {
        stopStreaming()
        _state.value = _state.value.copy(currentId = null)
    }

    fun switchChat(id: String) {
        stopStreaming()
        _state.value = _state.value.copy(currentId = id)
    }

    fun deleteChat(id: String) {
        stopStreaming()
        val remaining = _state.value.conversations.filterNot { it.id == id }
        persistConversations(remaining)
        _state.value = _state.value.copy(
            conversations = remaining,
            currentId = if (_state.value.currentId == id) remaining.firstOrNull()?.id
            else _state.value.currentId,
        )
    }

    private fun mutateCurrent(persist: Boolean = true, transform: (List<UiMessage>) -> List<UiMessage>) {
        val s = _state.value
        val id = s.currentId ?: return
        val updated = s.conversations.map {
            if (it.id == id) it.copy(messages = transform(it.messages)) else it
        }
        // per-token JSON encodes of 50 conversations would grind the DC-1;
        // stream deltas skip disk and the terminal event persists everything
        if (persist) persistConversations(updated)
        _state.value = s.copy(conversations = updated)
    }

    // --- chat ---------------------------------------------------------------

    fun send(text: String) {
        val trimmed = text.trim()
        val model = _state.value.selectedModel
        if (trimmed.isEmpty() || _state.value.streaming) return
        if (model == null) {
            _state.value = _state.value.copy(connectionError = "No model selected — check server settings")
            return
        }

        // lazily create the conversation on first message
        if (_state.value.currentId == null) {
            val conv = Conversation(
                id = UUID.randomUUID().toString(),
                title = trimmed.take(42),
            )
            val convs = listOf(conv) + _state.value.conversations
            persistConversations(convs)
            _state.value = _state.value.copy(conversations = convs, currentId = conv.id)
        }

        mutateCurrent { it + UiMessage("user", trimmed) + UiMessage("assistant", "") }
        _state.value = _state.value.copy(streaming = true, connectionError = null, draft = "")

        // failed bubbles hold OUR meta-text ("no answer — …"), not the model's
        // words; replaying them as assistant turns poisons the context and
        // sends small models into reasoning spirals
        val history = _state.value.currentMessages
            .dropLast(1)
            .filterNot { it.failed }
            .map { ChatMessage(it.role, it.content) }
        streamJob = viewModelScope.launch {
            client.streamChat(model, history, _state.value.temperature).collect { event ->
                when (event) {
                    is StreamEvent.Token -> mutateCurrent(persist = false) { msgs ->
                        val last = msgs.last()
                        msgs.dropLast(1) + last.copy(content = last.content + event.text)
                    }
                    is StreamEvent.Reasoning -> mutateCurrent(persist = false) { msgs ->
                        val last = msgs.last()
                        msgs.dropLast(1) + last.copy(thinking = (last.thinking + event.text).takeLast(200))
                    }
                    is StreamEvent.Done -> {
                        // a reasoning model can burn its whole budget thinking
                        // and never answer — say so instead of leaving a blank
                        mutateCurrent { msgs ->
                            val last = msgs.last()
                            if (last.role == "assistant" && last.content.isEmpty())
                                msgs.dropLast(1) + last.copy(
                                    content = "(no answer — the model spent its whole budget thinking; try asking more directly)",
                                    failed = true,
                                )
                            else msgs
                        }
                        _state.value = _state.value.copy(streaming = false)
                    }
                    is StreamEvent.Error -> {
                        mutateCurrent { msgs ->
                            val last = msgs.last()
                            val content = if (last.content.isEmpty()) "⚠ ${event.message}"
                            else "${last.content}\n\n⚠ interrupted: ${event.message}"
                            msgs.dropLast(1) + last.copy(content = content, failed = true)
                        }
                        _state.value = _state.value.copy(streaming = false)
                    }
                }
            }
        }
    }

    fun stopStreaming() {
        streamJob?.cancel()
        mutateCurrent { it }  // flush partial stream content to disk
        _state.value = _state.value.copy(streaming = false)
    }

    fun clearChat() {
        stopStreaming()
        mutateCurrent { emptyList() }
    }
}
