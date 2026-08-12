package computer.zero.chat.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.Send
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.input.key.Key
import androidx.compose.ui.input.key.KeyEventType
import androidx.compose.ui.input.key.isShiftPressed
import androidx.compose.ui.input.key.key
import androidx.compose.ui.input.key.onPreviewKeyEvent
import androidx.compose.ui.input.key.type
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import computer.zero.chat.ChatUiState
import computer.zero.chat.ChatViewModel
import computer.zero.chat.UiMessage

/** The message list + composer, shared by phone and tablet layouts. */
@Composable
fun ChatColumn(
    vm: ChatViewModel,
    state: ChatUiState,
    modifier: Modifier = Modifier,
    bubbleMaxWidth: Dp = 320.dp,
    contentMaxWidth: Dp = Dp.Unspecified,
) {
    val input = state.draft
    val listState = rememberLazyListState()
    val messages = state.currentMessages

    // follow the stream only when already at the bottom — never hijack a
    // reader who scrolled up mid-generation
    LaunchedEffect(messages.size) {
        if (messages.isNotEmpty()) listState.animateScrollToItem(messages.lastIndex)
    }
    LaunchedEffect(messages.lastOrNull()?.content?.length, messages.lastOrNull()?.thinking?.length) {
        if (messages.isNotEmpty() && !listState.canScrollForward) {
            listState.animateScrollToItem(messages.lastIndex)
        }
    }

    Column(
        modifier
            .imePadding()
            .widthIn(max = contentMaxWidth),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        state.connectionError?.let {
            Card(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(8.dp),
                colors = CardDefaults.cardColors(
                    containerColor = MaterialTheme.colorScheme.errorContainer,
                ),
            ) {
                Text(
                    it,
                    Modifier.padding(12.dp),
                    color = MaterialTheme.colorScheme.onErrorContainer,
                    style = MaterialTheme.typography.bodySmall,
                )
            }
        }

        LazyColumn(
            state = listState,
            modifier = Modifier
                .weight(1f)
                .fillMaxWidth(),
            contentPadding = PaddingValues(12.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            if (messages.isEmpty()) {
                item {
                    Text(
                        if (state.connected) "Ask anything — it stays on your machine."
                        else "Connect to your model server to start.",
                        Modifier
                            .fillMaxWidth()
                            .padding(top = 48.dp),
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.outline,
                        textAlign = androidx.compose.ui.text.style.TextAlign.Center,
                    )
                }
            }
            items(messages) { msg -> MessageBubble(msg, bubbleMaxWidth) }
        }

        Row(
            Modifier
                .fillMaxWidth()
                .padding(8.dp),
            verticalAlignment = Alignment.Bottom,
        ) {
            // Enter sends, Shift+Enter breaks the line — the DC-1 lives in a
            // keyboard case, so this is the primary send path there.
            OutlinedTextField(
                value = input,
                onValueChange = { vm.updateDraft(it) },
                modifier = Modifier
                    .weight(1f)
                    .onPreviewKeyEvent { event ->
                        if (event.type == KeyEventType.KeyDown &&
                            event.key == Key.Enter && !event.isShiftPressed &&
                            input.isNotBlank() && !state.streaming
                        ) {
                            vm.send(input)
                            true
                        } else false
                    },
                placeholder = { Text("Message…") },
                maxLines = 5,
            )
            if (state.streaming) {
                IconButton(onClick = { vm.stopStreaming() }) {
                    CircularProgressIndicator(Modifier.padding(4.dp))
                }
            } else {
                IconButton(
                    onClick = { vm.send(input) },
                    enabled = input.isNotBlank(),
                ) {
                    Icon(Icons.AutoMirrored.Filled.Send, contentDescription = "Send")
                }
            }
        }
    }
}

/**
 * Grayscale-first bubbles for the DC-1's LivePaper display: the user's
 * messages are solid ink (inverse surface), the model's are outlined paper.
 * Distinction by fill and border, never by hue.
 */
@Composable
fun MessageBubble(msg: UiMessage, maxWidth: Dp) {
    val fromUser = msg.role == "user"
    Row(
        Modifier.fillMaxWidth(),
        horizontalArrangement = if (fromUser) Arrangement.End else Arrangement.Start,
    ) {
        Card(
            shape = RoundedCornerShape(14.dp),
            colors = CardDefaults.cardColors(
                containerColor = if (fromUser) MaterialTheme.colorScheme.inverseSurface
                else MaterialTheme.colorScheme.surface,
                contentColor = if (fromUser) MaterialTheme.colorScheme.inverseOnSurface
                else MaterialTheme.colorScheme.onSurface,
            ),
            border = if (fromUser) null else androidx.compose.foundation.BorderStroke(
                1.dp,
                if (msg.failed) MaterialTheme.colorScheme.error
                else MaterialTheme.colorScheme.outlineVariant,
            ),
            modifier = Modifier.widthIn(max = maxWidth),
        ) {
            // while the model reasons, show the live tail of its thinking in
            // dim italics; the real answer replaces it when content arrives
            if (msg.content.isEmpty() && msg.thinking.isNotEmpty()) {
                Text(
                    "…" + msg.thinking.trim(),
                    Modifier.padding(horizontal = 12.dp, vertical = 8.dp),
                    style = MaterialTheme.typography.bodySmall,
                    fontStyle = FontStyle.Italic,
                    color = MaterialTheme.colorScheme.outline,
                )
            } else {
                Text(
                    msg.content.ifEmpty { "thinking…" },
                    Modifier.padding(horizontal = 12.dp, vertical = 8.dp),
                    style = MaterialTheme.typography.bodyMedium,
                )
            }
        }
    }
}
