package computer.zero.chat.her

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp

/**
 * Her on the phone: one glance line, the full line, her question (with its
 * own answer box — answering her and asking Zero are different acts), and
 * Zero's last answer. Grayscale, like the rest of the app.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HerScreen(vm: HerViewModel, onOpenChat: () -> Unit) {
    val s by vm.state.collectAsState()
    Scaffold(topBar = {
        TopAppBar(
            title = { Text(s.snapshot?.name ?: "Her") },
            actions = { TextButton(onClick = onOpenChat) { Text("Models") } },
        )
    }) { padding ->
        Column(
            Modifier.fillMaxSize().padding(padding).padding(16.dp).verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            if (!s.paired) PairPane(vm) else PresencePane(vm)
        }
    }
}

@Composable
private fun PairPane(vm: HerViewModel) {
    val s by vm.state.collectAsState()
    var url by rememberSaveable { mutableStateOf(s.baseUrl.ifEmpty { "http://192.168.1.2:7770" }) }
    var code by rememberSaveable { mutableStateOf("") }
    Text("On your Mac, run  her pair  — it shows an address and a six-letter code.",
        style = MaterialTheme.typography.bodyMedium)
    OutlinedTextField(value = url, onValueChange = { url = it }, label = { Text("Mac address") },
        singleLine = true, modifier = Modifier.fillMaxWidth())
    OutlinedTextField(value = code, onValueChange = { code = it.uppercase() }, label = { Text("Code") },
        singleLine = true, modifier = Modifier.fillMaxWidth())
    Button(
        onClick = { vm.setBaseUrl(url); vm.pair(code) },
        enabled = !s.busy && code.length >= 6,
        modifier = Modifier.fillMaxWidth(),
    ) { Text(if (s.busy) "Pairing…" else "Pair this phone") }
    s.error?.let { Text(it, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall) }
    Text("Pairing lets this phone ask her anything over your own wifi. It can never change the Mac: " +
        "anything from a phone waits for a yes given at the Mac.",
        style = MaterialTheme.typography.bodySmall)
}

@Composable
private fun PresencePane(vm: HerViewModel) {
    val s by vm.state.collectAsState()
    val snap = s.snapshot
    val presence = snap?.presence
    val alive = snap?.alive == true
    // two boxes, two drafts: answering her and asking Zero are different acts
    var answer by rememberSaveable { mutableStateOf("") }
    var ask by rememberSaveable { mutableStateOf("") }

    Text(if (alive) (snap.status.ifEmpty { "ready" }) else "asleep",
        style = MaterialTheme.typography.labelMedium)
    Text(presence?.glance ?: "…", style = MaterialTheme.typography.headlineMedium)
    Text(presence?.line ?: (s.error ?: "Connecting to your Mac…"),
        style = MaterialTheme.typography.bodyMedium)

    presence?.question?.let { q ->
        HorizontalDivider()
        Text("She asks: ${q.text}", style = MaterialTheme.typography.bodyLarge)
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedTextField(value = answer, onValueChange = { answer = it },
                placeholder = { Text("Answer her") }, singleLine = true,
                modifier = Modifier.weight(1f))
            Button(onClick = { vm.say(answer, answerHer = true); answer = "" },
                enabled = !s.busy && answer.isNotBlank()) { Text("Tell her") }
        }
        TextButton(onClick = { vm.say("skip", answerHer = true) }) { Text("Skip this one") }
    }

    HorizontalDivider()
    snap?.answer?.text?.takeIf { it.isNotEmpty() }?.let {
        Text("Zero › $it", style = MaterialTheme.typography.bodyMedium)
    }
    if (s.pendingSince != null) Text("thinking…", style = MaterialTheme.typography.bodySmall)
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        OutlinedTextField(value = ask, onValueChange = { ask = it },
            placeholder = { Text("Ask Zero anything") }, singleLine = true,
            modifier = Modifier.weight(1f))
        Button(onClick = { vm.say(ask, answerHer = false); ask = "" },
            enabled = !s.busy && ask.isNotBlank()) { Text("Ask") }
    }
    s.error?.let { Text(it, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall) }
    if (!alive) Text("Your Mac is asleep. What you send waits for it there.",
        style = MaterialTheme.typography.bodySmall)
    Spacer(Modifier.width(1.dp))
    OutlinedButton(onClick = vm::unpair) { Text("Forget this Mac") }
}
