package computer.zero.chat

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import computer.zero.chat.her.HerScreen
import computer.zero.chat.her.HerViewModel
import computer.zero.chat.ui.ChatScreen
import computer.zero.chat.ui.SettingsScreen
import computer.zero.chat.ui.TabletScreen

// Grayscale-first palettes for the DC-1's LivePaper display: ink on paper by
// day, paper on ink under the amber night light. Hue carries no meaning.
private val PaperLight = lightColorScheme(
    background = Color(0xFFFFFFFF),
    surface = Color(0xFFFFFFFF),
    onBackground = Color(0xFF111111),
    onSurface = Color(0xFF111111),
    surfaceVariant = Color(0xFFEDEDED),
    onSurfaceVariant = Color(0xFF222222),
    inverseSurface = Color(0xFF141414),
    inverseOnSurface = Color(0xFFFAFAFA),
    primary = Color(0xFF141414),
    onPrimary = Color(0xFFFAFAFA),
    outline = Color(0xFF555555),
    outlineVariant = Color(0xFFBBBBBB),
)

private val PaperDark = darkColorScheme(
    background = Color(0xFF0B0B0B),
    surface = Color(0xFF0B0B0B),
    onBackground = Color(0xFFEDEDED),
    onSurface = Color(0xFFEDEDED),
    surfaceVariant = Color(0xFF232323),
    onSurfaceVariant = Color(0xFFDDDDDD),
    inverseSurface = Color(0xFFEDEDED),
    inverseOnSurface = Color(0xFF111111),
    primary = Color(0xFFEDEDED),
    onPrimary = Color(0xFF111111),
    outline = Color(0xFF9A9A9A),
    outlineVariant = Color(0xFF3A3A3A),
)

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            // Paper is the product: the DC-1's LivePaper panel wants ink-on-white.
            // PaperDark stays for a future amber-night toggle; system dark mode
            // is deliberately not honored (family devices end up in odd states).
            MaterialTheme(colorScheme = PaperLight) {
                val vm: ChatViewModel = viewModel()
                val herVm: HerViewModel = viewModel()
                // rememberSaveable: fold/unfold recreates the activity and a
                // plain remember{} would silently close the settings screen
                var showSettings by rememberSaveable { mutableStateOf(false) }
                // Her is the front door on a phone; the model chat (talking
                // to a bare model server) stays one tap away for the curious
                var showHer by rememberSaveable { mutableStateOf(true) }

                // the Surface paints the panes; without it the manifest
                // theme's window background bleeds through every gap
                Surface(color = MaterialTheme.colorScheme.background) {
                    BoxWithConstraints {
                    when {
                        // canonical expanded width, gated on height so a
                        // landscape phone/Fold-cover never gets the sidebar
                        maxWidth >= 840.dp && maxHeight >= 480.dp ->
                            TabletScreen(vm, showServerPane = true)
                        // medium width: Pixel Fold inner display lands here
                        maxWidth >= 600.dp && maxHeight >= 480.dp -> {
                            if (showSettings) {
                                SettingsScreen(vm = vm, onDone = { showSettings = false })
                            } else {
                                TabletScreen(
                                    vm,
                                    showServerPane = false,
                                    onOpenSettings = { showSettings = true },
                                )
                            }
                        }
                        // phone
                        else -> {
                            if (showSettings) {
                                SettingsScreen(vm = vm, onDone = { showSettings = false })
                            } else if (showHer) {
                                HerScreen(vm = herVm, onOpenChat = { showHer = false })
                            } else {
                                ChatScreen(vm = vm, onOpenSettings = { showSettings = true })
                            }
                        }
                        }
                    }
                }
            }
        }
    }
}
