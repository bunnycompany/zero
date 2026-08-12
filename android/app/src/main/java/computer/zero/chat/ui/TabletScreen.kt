package computer.zero.chat.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Slider
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.VerticalDivider
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Clear
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.Settings
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import computer.zero.chat.ChatUiState
import computer.zero.chat.ChatViewModel

/**
 * Three-pane layout for the Daylight DC-1 (and tablets generally):
 * conversations | chat | server & models. Grayscale-first: structure is
 * carried by borders and fills, never by hue.
 */
@Composable
fun TabletScreen(
    vm: ChatViewModel,
    showServerPane: Boolean,
    onOpenSettings: (() -> Unit)? = null,
) {
    val state by vm.state.collectAsState()

    Row(Modifier.fillMaxSize().safeDrawingPadding()) {
        SidebarPane(vm, state, Modifier.width(252.dp).fillMaxHeight())
        VerticalDivider()
        Column(Modifier.weight(1f)) {
            ChatHeader(vm, state, onOpenSettings)
            HorizontalDivider()
            ChatColumn(
                vm = vm,
                state = state,
                modifier = Modifier
                    .weight(1f)
                    .fillMaxWidth()
                    .padding(horizontal = 24.dp),
                bubbleMaxWidth = 560.dp,
                contentMaxWidth = 820.dp,
            )
        }
        if (showServerPane) {
            VerticalDivider()
            ServerPane(vm, state, Modifier.width(300.dp).fillMaxHeight())
        }
    }
}

@Composable
private fun ChatHeader(vm: ChatViewModel, state: ChatUiState, onOpenSettings: (() -> Unit)? = null) {
    var modelMenuOpen by remember { mutableStateOf(false) }
    Row(
        Modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp, vertical = 6.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            state.conversations.firstOrNull { it.id == state.currentId }?.title ?: "New chat",
            style = MaterialTheme.typography.titleMedium,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
            modifier = Modifier.weight(1f),
        )
        Box {
            TextButton(onClick = { modelMenuOpen = true }) {
                Text(
                    state.selectedModel?.substringAfterLast('/') ?: "no model",
                    style = MaterialTheme.typography.labelLarge,
                )
            }
            DropdownMenu(expanded = modelMenuOpen, onDismissRequest = { modelMenuOpen = false }) {
                state.models.forEach { m ->
                    DropdownMenuItem(
                        text = { Text(m) },
                        onClick = {
                            vm.selectModel(m)
                            modelMenuOpen = false
                        },
                    )
                }
            }
        }
        IconButton(onClick = { vm.clearChat() }) {
            Icon(Icons.Filled.Clear, contentDescription = "Clear conversation")
        }
        onOpenSettings?.let {
            IconButton(onClick = it) {
                Icon(Icons.Filled.Settings, contentDescription = "Settings")
            }
        }
    }
}

@Composable
internal fun SidebarPane(vm: ChatViewModel, state: ChatUiState, modifier: Modifier) {
    Column(modifier.padding(12.dp)) {
        Text(
            "Zero",
            style = MaterialTheme.typography.titleLarge,
            fontWeight = FontWeight.Bold,
            modifier = Modifier.padding(start = 4.dp, top = 4.dp, bottom = 12.dp),
        )
        OutlinedButton(
            onClick = { vm.newChat() },
            modifier = Modifier.fillMaxWidth(),
        ) {
            Icon(Icons.Filled.Add, contentDescription = null, Modifier.size(18.dp))
            Spacer(Modifier.width(8.dp))
            Text("New chat")
        }
        Spacer(Modifier.height(12.dp))

        LazyColumn(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            items(state.conversations, key = { it.id }) { conv ->
                val selected = conv.id == state.currentId
                Row(
                    Modifier
                        .fillMaxWidth()
                        .background(
                            if (selected) MaterialTheme.colorScheme.surfaceVariant
                            else MaterialTheme.colorScheme.surface,
                            RoundedCornerShape(8.dp),
                        )
                        .clickable { vm.switchChat(conv.id) }
                        .padding(start = 12.dp, top = 4.dp, bottom = 4.dp, end = 4.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Text(
                        conv.title,
                        style = MaterialTheme.typography.bodyMedium,
                        fontWeight = if (selected) FontWeight.SemiBold else FontWeight.Normal,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                        modifier = Modifier.weight(1f),
                    )
                    IconButton(onClick = { vm.deleteChat(conv.id) }, modifier = Modifier.size(28.dp)) {
                        Icon(
                            Icons.Filled.Delete,
                            contentDescription = "Delete",
                            Modifier.size(16.dp),
                            tint = MaterialTheme.colorScheme.outline,
                        )
                    }
                }
            }
        }

        HorizontalDivider(Modifier.padding(vertical = 8.dp))
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(
                Modifier
                    .size(9.dp)
                    .background(
                        if (state.connected) MaterialTheme.colorScheme.onSurface
                        else MaterialTheme.colorScheme.outlineVariant,
                        CircleShape,
                    )
            )
            Spacer(Modifier.width(8.dp))
            Text(
                if (state.connected) "Connected · ${state.models.size} models"
                else "Offline",
                style = MaterialTheme.typography.labelMedium,
                color = MaterialTheme.colorScheme.outline,
            )
        }
    }
}

@Composable
private fun ServerPane(vm: ChatViewModel, state: ChatUiState, modifier: Modifier) {
    var baseUrl by rememberSaveable(state.baseUrl) { mutableStateOf(state.baseUrl) }
    var apiKey by rememberSaveable(state.apiKey) { mutableStateOf(state.apiKey) }

    Column(modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Text("SERVER", style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.outline)
        OutlinedTextField(
            value = baseUrl,
            onValueChange = { baseUrl = it },
            modifier = Modifier.fillMaxWidth(),
            label = { Text("Base URL") },
            singleLine = true,
            textStyle = MaterialTheme.typography.bodySmall,
        )
        OutlinedTextField(
            value = apiKey,
            onValueChange = { apiKey = it },
            modifier = Modifier.fillMaxWidth(),
            label = { Text("API key (optional)") },
            singleLine = true,
            textStyle = MaterialTheme.typography.bodySmall,
        )
        Button(
            onClick = { vm.updateSettings(baseUrl.trim(), apiKey.trim()) },
            modifier = Modifier.fillMaxWidth(),
        ) { Text("Save & test") }

        HorizontalDivider(Modifier.padding(vertical = 4.dp))
        Text("MODELS", style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.outline)
        LazyColumn(Modifier.weight(1f)) {
            items(state.models, key = { it }) { m ->
                Row(
                    Modifier
                        .fillMaxWidth()
                        .clickable { vm.selectModel(m) },
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    RadioButton(selected = m == state.selectedModel, onClick = { vm.selectModel(m) })
                    Text(
                        m.substringAfterLast('/'),
                        style = MaterialTheme.typography.bodySmall,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
            }
        }

        HorizontalDivider(Modifier.padding(vertical = 4.dp))
        Text(
            "TEMPERATURE · %.1f".format(state.temperature),
            style = MaterialTheme.typography.labelMedium,
            color = MaterialTheme.colorScheme.outline,
        )
        Slider(
            value = state.temperature.toFloat(),
            onValueChange = { vm.setTemperature(it.toDouble()) },
            valueRange = 0f..1.5f,
        )
    }
}
