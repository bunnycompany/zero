package computer.zero.chat.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import computer.zero.chat.ChatViewModel

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SettingsScreen(vm: ChatViewModel, onDone: () -> Unit) {
    val state by vm.state.collectAsState()
    var baseUrl by rememberSaveable { mutableStateOf(state.baseUrl) }
    var apiKey by rememberSaveable { mutableStateOf(state.apiKey) }

    Scaffold(
        topBar = { TopAppBar(title = { Text("Settings") }) },
    ) { padding ->
        Column(
            Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            OutlinedTextField(
                value = baseUrl,
                onValueChange = { baseUrl = it },
                modifier = Modifier.fillMaxWidth(),
                label = { Text("Server base URL") },
                placeholder = { Text("http://<mac-ip>:8080/v1") },
                singleLine = true,
            )
            OutlinedTextField(
                value = apiKey,
                onValueChange = { apiKey = it },
                modifier = Modifier.fillMaxWidth(),
                label = { Text("API key (optional)") },
                singleLine = true,
            )
            Text(
                "Run scripts/serve_models.sh on the Mac; it prints the URL to enter here. " +
                    "Phone and Mac must be on the same network.",
                style = MaterialTheme.typography.bodySmall,
            )
            Button(
                onClick = {
                    vm.updateSettings(baseUrl.trim(), apiKey.trim())
                    onDone()
                },
                modifier = Modifier.fillMaxWidth(),
            ) {
                Text("Save & test connection")
            }
            state.connectionError?.let {
                Text(it, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall)
            }
            if (state.models.isNotEmpty()) {
                Text(
                    "Connected — ${state.models.size} model(s) available",
                    style = MaterialTheme.typography.bodySmall,
                )
            }
        }
    }
}
