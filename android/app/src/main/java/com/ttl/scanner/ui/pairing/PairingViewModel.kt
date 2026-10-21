package com.ttl.scanner.ui.pairing

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.ttl.scanner.data.api.NetworkClient
import com.ttl.scanner.data.api.PairRequest
import com.ttl.scanner.data.pref.PreferenceManager
import com.ttl.scanner.data.repository.MaterialRepository
import com.ttl.scanner.util.QrPayloadParser
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

data class PairingUiState(
    val serverAddress: String = "",
    val pairingCode: String = "",
    val deviceName: String = "",
    val isLoading: Boolean = false,
    val errorMessage: String? = null,
    val isSuccess: Boolean = false
)

class PairingViewModel(
    private val prefManager: PreferenceManager,
    private val networkClient: NetworkClient,
    private val materialRepository: MaterialRepository
) : ViewModel() {

    private val _uiState = MutableStateFlow(
        PairingUiState(
            serverAddress = prefManager.getServerAddress() ?: "",
            deviceName = prefManager.getDeviceName()
        )
    )
    val uiState: StateFlow<PairingUiState> = _uiState.asStateFlow()

    fun onAddressChange(address: String) {
        _uiState.value = _uiState.value.copy(serverAddress = address, errorMessage = null)
    }

    fun onCodeChange(code: String) {
        if (code.length <= 6 && code.all { it.isDigit() }) {
            _uiState.value = _uiState.value.copy(pairingCode = code, errorMessage = null)
        }
    }

    fun onDeviceNameChange(name: String) {
        _uiState.value = _uiState.value.copy(deviceName = name, errorMessage = null)
    }

    fun onQrScanned(qrText: String) {
        val parsed = QrPayloadParser.parse(qrText) ?: run {
            _uiState.value = _uiState.value.copy(errorMessage = "Invalid pairing QR code format.")
            return
        }

        val existingId = prefManager.getInstallationId()

        // 1. Re-scan of QR with SAME installation ID -> address-only update (keeps token!)
        if (parsed.installationId != null && parsed.installationId == existingId && prefManager.getToken() != null) {
            prefManager.updateServerAddress(parsed.url)
            _uiState.value = _uiState.value.copy(
                serverAddress = parsed.url,
                isSuccess = true
            )
            return
        }

        // 2. Full pairing QR
        _uiState.value = _uiState.value.copy(
            serverAddress = parsed.url,
            pairingCode = parsed.code ?: _uiState.value.pairingCode,
            errorMessage = null
        )

        if (!parsed.code.isNullOrBlank() && parsed.code.length == 6) {
            submitPairing(installationId = parsed.installationId)
        }
    }

    fun submitPairing(installationId: String? = null) {
        val state = _uiState.value
        val address = state.serverAddress.trim().trimEnd('/')
        val code = state.pairingCode.trim()
        val deviceName = state.deviceName.trim().ifEmpty { "Android Scanner" }

        if (address.isBlank() || (!address.startsWith("http://") && !address.startsWith("https://"))) {
            _uiState.value = state.copy(errorMessage = "Please enter a valid server URL starting with https:// or http://")
            return
        }
        if (code.length != 6 || !code.all { it.isDigit() }) {
            _uiState.value = state.copy(errorMessage = "Pairing code must be 6 digits.")
            return
        }

        _uiState.value = state.copy(isLoading = true, errorMessage = null)

        viewModelScope.launch {
            try {
                val api = networkClient.createService(baseUrl = address)
                val response = api.pairDevice(PairRequest(code = code, deviceName = deviceName))

                if (response.isSuccessful && response.body()?.success == true) {
                    val token = response.body()!!.token!!
                    val finalInstId = installationId ?: prefManager.getInstallationId() ?: java.util.UUID.randomUUID().toString()
                    prefManager.savePairing(
                        token = token,
                        address = address,
                        installationId = finalInstId,
                        deviceName = deviceName
                    )

                    // Trigger initial material sync in background
                    materialRepository.refreshMaterials()

                    _uiState.value = _uiState.value.copy(
                        isLoading = false,
                        isSuccess = true
                    )
                } else {
                    val err = response.body()?.message ?: "Pairing failed (HTTP ${response.code()})"
                    _uiState.value = _uiState.value.copy(
                        isLoading = false,
                        errorMessage = err
                    )
                }
            } catch (e: Exception) {
                _uiState.value = _uiState.value.copy(
                    isLoading = false,
                    errorMessage = "Cannot reach desktop: ${e.message ?: "Network error"}"
                )
            }
        }
    }
}
