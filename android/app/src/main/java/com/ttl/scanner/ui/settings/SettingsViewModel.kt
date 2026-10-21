package com.ttl.scanner.ui.settings

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.ttl.scanner.data.local.AppDatabase
import com.ttl.scanner.data.pref.PreferenceManager
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

data class SettingsUiState(
    val deviceName: String = "",
    val serverAddress: String = "",
    val installationId: String = "",
    val appVersion: String = "1.0.0",
    val isUnpaired: Boolean = false
)

class SettingsViewModel(
    private val prefManager: PreferenceManager,
    private val database: AppDatabase
) : ViewModel() {

    private val _uiState = MutableStateFlow(
        SettingsUiState(
            deviceName = prefManager.getDeviceName(),
            serverAddress = prefManager.getServerAddress() ?: "",
            installationId = prefManager.getInstallationId() ?: "None"
        )
    )
    val uiState: StateFlow<SettingsUiState> = _uiState.asStateFlow()

    fun onDeviceNameChange(name: String) {
        prefManager.setDeviceName(name)
        _uiState.value = _uiState.value.copy(deviceName = name)
    }

    fun onAddressChange(address: String) {
        prefManager.updateServerAddress(address)
        _uiState.value = _uiState.value.copy(serverAddress = address)
    }

    fun unpair() {
        viewModelScope.launch {
            prefManager.clearPairing()
            database.scanEventDao().clearAll()
            database.materialDao().clearAll()
            _uiState.value = _uiState.value.copy(isUnpaired = true)
        }
    }
}
