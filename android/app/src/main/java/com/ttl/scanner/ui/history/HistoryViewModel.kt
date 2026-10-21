package com.ttl.scanner.ui.history

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.ttl.scanner.data.local.ScanEventEntity
import com.ttl.scanner.data.repository.ScanRepository
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

class HistoryViewModel(
    private val scanRepository: ScanRepository
) : ViewModel() {

    val scans: StateFlow<List<ScanEventEntity>> = scanRepository.getAllScansFlow()
        .stateIn(viewModelScope, SharingStarted.Lazily, emptyList())

    private val _isRefreshing = MutableStateFlow(false)
    val isRefreshing: StateFlow<Boolean> = _isRefreshing.asStateFlow()

    init {
        startPolling()
    }

    fun refresh() {
        viewModelScope.launch {
            _isRefreshing.value = true
            scanRepository.syncPendingQueue()
            scanRepository.pollSentScans()
            _isRefreshing.value = false
        }
    }

    private fun startPolling() {
        viewModelScope.launch {
            while (isActive) {
                scanRepository.pollSentScans()
                delay(3000) // Poll status every 3 seconds while viewing history
            }
        }
    }
}
