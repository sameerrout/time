package com.ttl.scanner.ui.home

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.ttl.scanner.data.api.NetworkClient
import com.ttl.scanner.data.local.AppDatabase
import com.ttl.scanner.data.pref.PreferenceManager
import com.ttl.scanner.data.repository.MaterialRepository
import com.ttl.scanner.data.repository.ScanRepository
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

data class HomeUiState(
    val isPcReachable: Boolean = false,
    val isCheckingConnection: Boolean = true,
    val serverAddress: String = "",
    val deviceName: String = "",
    val materialCount: Int = 0,
    val pendingScanCount: Int = 0,
    val lastSyncMessage: String? = null
)

class HomeViewModel(
    private val prefManager: PreferenceManager,
    private val networkClient: NetworkClient,
    private val materialRepository: MaterialRepository,
    private val scanRepository: ScanRepository,
    private val database: AppDatabase
) : ViewModel() {

    private val _uiState = MutableStateFlow(
        HomeUiState(
            serverAddress = prefManager.getServerAddress() ?: "Not configured",
            deviceName = prefManager.getDeviceName()
        )
    )
    val uiState: StateFlow<HomeUiState> = _uiState.asStateFlow()

    init {
        loadData()
        startPeriodicHealthCheck()
    }

    fun loadData() {
        viewModelScope.launch {
            val count = database.materialDao().getCount()
            val pending = database.scanEventDao().getPendingScans().size
            _uiState.value = _uiState.value.copy(
                serverAddress = prefManager.getServerAddress() ?: "Not configured",
                deviceName = prefManager.getDeviceName(),
                materialCount = count,
                pendingScanCount = pending
            )
        }
    }

    fun checkConnection() {
        viewModelScope.launch {
            _uiState.value = _uiState.value.copy(isCheckingConnection = true)
            try {
                val api = networkClient.createService()
                val response = api.checkHealth()
                val reachable = response.isSuccessful && response.body()?.status == "ok"
                _uiState.value = _uiState.value.copy(
                    isPcReachable = reachable,
                    isCheckingConnection = false
                )
                if (reachable) {
                    // Also sync materials with ETag
                    materialRepository.refreshMaterials()
                    scanRepository.syncPendingQueue()
                    scanRepository.pollSentScans()
                    loadData()
                }
            } catch (e: Exception) {
                _uiState.value = _uiState.value.copy(
                    isPcReachable = false,
                    isCheckingConnection = false
                )
            }
        }
    }

    private fun startPeriodicHealthCheck() {
        viewModelScope.launch {
            while (isActive) {
                checkConnection()
                delay(60_000) // check and sync every 60 seconds
            }
        }
    }
}
