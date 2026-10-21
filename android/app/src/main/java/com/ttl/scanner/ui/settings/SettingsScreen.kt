package com.ttl.scanner.ui.settings

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.ttl.scanner.ui.theme.TextMuted

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SettingsScreen(
    viewModel: SettingsViewModel,
    onNavigateBack: () -> Unit,
    onUnpaired: () -> Unit
) {
    val state by viewModel.uiState.collectAsState()
    var showUnpairDialog by remember { mutableStateOf(false) }

    LaunchedEffect(state.isUnpaired) {
        if (state.isUnpaired) {
            onUnpaired()
        }
    }

    if (showUnpairDialog) {
        AlertDialog(
            onDismissRequest = { showUnpairDialog = false },
            title = { Text("Unpair Scanner Device?") },
            text = { Text("This will delete the stored authentication token and clear cached scans on this phone. You will need to pair again with the desktop.") },
            confirmButton = {
                Button(
                    onClick = {
                        showUnpairDialog = false
                        viewModel.unpair()
                    },
                    colors = ButtonDefaults.buttonColors(containerColor = Color(0xFFDC2626))
                ) {
                    Text("Unpair")
                }
            },
            dismissButton = {
                TextButton(onClick = { showUnpairDialog = false }) {
                    Text("Cancel")
                }
            }
        )
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Settings", fontWeight = FontWeight.Bold) },
                navigationIcon = {
                    IconButton(onClick = onNavigateBack) {
                        Icon(Icons.Default.ArrowBack, contentDescription = "Back")
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = Color.White)
            )
        }
    ) { paddingValues ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(paddingValues)
                .verticalScroll(rememberScrollState())
                .padding(20.dp),
            verticalArrangement = Arrangement.SpaceBetween
        ) {
            Column {
                Text(
                    text = "DEVICE & NETWORK CONFIGURATION",
                    style = MaterialTheme.typography.labelSmall,
                    color = TextMuted,
                    fontWeight = FontWeight.Bold
                )

                Spacer(modifier = Modifier.height(14.dp))

                OutlinedTextField(
                    value = state.deviceName,
                    onValueChange = viewModel::onDeviceNameChange,
                    label = { Text("Device Name") },
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(10.dp)
                )

                Spacer(modifier = Modifier.height(14.dp))

                OutlinedTextField(
                    value = state.serverAddress,
                    onValueChange = viewModel::onAddressChange,
                    label = { Text("Desktop Server Address (URL)") },
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(10.dp)
                )

                Spacer(modifier = Modifier.height(14.dp))

                OutlinedTextField(
                    value = state.installationId,
                    onValueChange = {},
                    label = { Text("PC Installation ID") },
                    modifier = Modifier.fillMaxWidth(),
                    readOnly = true,
                    shape = RoundedCornerShape(10.dp)
                )

                Spacer(modifier = Modifier.height(24.dp))

                Card(
                    colors = CardDefaults.cardColors(containerColor = Color(0xFFF1F5F9)),
                    shape = RoundedCornerShape(10.dp),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Column(modifier = Modifier.padding(14.dp)) {
                        Text("Application Version", fontWeight = FontWeight.SemiBold, fontSize = 14.sp)
                        Text("TTL Scanner v${state.appVersion}", fontSize = 13.sp, color = TextMuted)
                        Spacer(modifier = Modifier.height(6.dp))
                        Text(
                            "Zero data is stored in the cloud. All scan events flow directly into the local SQLite database on your computer.",
                            fontSize = 11.sp,
                            color = TextMuted
                        )
                    }
                }
            }

            // Unpair Button at the bottom
            Button(
                onClick = { showUnpairDialog = true },
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(top = 32.dp)
                    .height(50.dp),
                shape = RoundedCornerShape(10.dp),
                colors = ButtonDefaults.buttonColors(containerColor = Color(0xFFDC2626))
            ) {
                Text("Unpair Device from Desktop", fontWeight = FontWeight.Bold, fontSize = 15.sp)
            }
        }
    }
}
