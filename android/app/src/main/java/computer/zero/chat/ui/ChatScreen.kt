package computer.zero.chat.ui

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.DrawerValue
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalDrawerSheet
import androidx.compose.material3.ModalNavigationDrawer
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.rememberDrawerState
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Menu
import androidx.compose.material.icons.filled.Settings
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import computer.zero.chat.ChatViewModel
import kotlinx.coroutines.launch

/** Compact (phone / folded Fold) layout: single column with the conversation
 *  list in a drawer — multi-chat must exist on the cover display too. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ChatScreen(vm: ChatViewModel, onOpenSettings: () -> Unit) {
    val state by vm.state.collectAsState()
    var modelMenuOpen by remember { mutableStateOf(false) }
    val drawerState = rememberDrawerState(DrawerValue.Closed)
    val scope = rememberCoroutineScope()

    // close the drawer when a conversation is picked
    LaunchedEffect(state.currentId) { drawerState.close() }

    ModalNavigationDrawer(
        drawerState = drawerState,
        drawerContent = {
            ModalDrawerSheet(drawerContainerColor = MaterialTheme.colorScheme.surface) {
                SidebarPane(vm, state, Modifier.fillMaxHeight())
            }
        },
    ) {
        Scaffold(
            topBar = {
                TopAppBar(
                    navigationIcon = {
                        IconButton(onClick = { scope.launch { drawerState.open() } }) {
                            Icon(Icons.Filled.Menu, contentDescription = "Conversations")
                        }
                    },
                    title = {
                        Column {
                            Text("Zero Chat", style = MaterialTheme.typography.titleMedium)
                            Box {
                                TextButton(onClick = { modelMenuOpen = true }) {
                                    Text(
                                        state.selectedModel?.substringAfterLast('/') ?: "no model",
                                        style = MaterialTheme.typography.labelMedium,
                                    )
                                }
                                DropdownMenu(
                                    expanded = modelMenuOpen,
                                    onDismissRequest = { modelMenuOpen = false },
                                ) {
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
                        }
                    },
                    actions = {
                        IconButton(onClick = onOpenSettings) {
                            Icon(Icons.Filled.Settings, contentDescription = "Settings")
                        }
                    },
                )
            },
        ) { padding ->
            ChatColumn(
                vm = vm,
                state = state,
                modifier = Modifier
                    .fillMaxSize()
                    .padding(padding),
                bubbleMaxWidth = 320.dp,
            )
        }
    }
}
