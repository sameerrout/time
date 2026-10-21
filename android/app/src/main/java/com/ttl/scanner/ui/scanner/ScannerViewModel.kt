package com.ttl.scanner.ui.scanner

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.ttl.scanner.data.local.MaterialEntity
import com.ttl.scanner.data.repository.MaterialRepository
import com.ttl.scanner.data.repository.ScanRepository
import com.ttl.scanner.util.SoundManager
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

data class ScannerUiState(
    val mode: String = "ISSUE", // "ISSUE" or "RECEIVE"
    val isTorchOn: Boolean = false,
    val isSearchingManually: Boolean = false,
    val searchQuery: String = "",
    val searchResults: List<MaterialEntity> = emptyList(),
    val showConfirmSheet: Boolean = false,
    val selectedMaterial: MaterialEntity? = null,

    // Issue fields
    val issueQty: String = "1.0",
    val requiredQty: String = "1.0",
    val purpose: String = "Production",
    val isOverStockWarning: Boolean = false,

    // Receive / Purchase Order fields
    val receiveQty: String = "1.0",
    val unitPrice: String = "0.0",
    val gstPct: String = "0.0",
    val supplier: String = "",
    val poNumber: String = "",
    val challanNo: String = "",

    val submissionMessage: String? = null
)

class ScannerViewModel(
    val mode: String,
    private val materialRepository: MaterialRepository,
    private val scanRepository: ScanRepository,
    private val soundManager: SoundManager
) : ViewModel() {

    private val _uiState = MutableStateFlow(ScannerUiState(mode = mode.uppercase()))
    val uiState: StateFlow<ScannerUiState> = _uiState.asStateFlow()

    private var lastScannedCode: String? = null
    private var lastScanTimestamp: Long = 0

    fun toggleTorch() {
        _uiState.value = _uiState.value.copy(isTorchOn = !_uiState.value.isTorchOn)
    }

    fun setSearchMode(enabled: Boolean) {
        _uiState.value = _uiState.value.copy(
            isSearchingManually = enabled,
            searchQuery = "",
            searchResults = emptyList()
        )
    }

    fun onSearchQueryChanged(query: String) {
        _uiState.value = _uiState.value.copy(searchQuery = query)
        viewModelScope.launch {
            val results = materialRepository.searchMaterials(query)
            _uiState.value = _uiState.value.copy(searchResults = results)
        }
    }

    fun onMaterialSelected(material: MaterialEntity) {
        setSearchMode(false)
        openConfirmSheet(material)
    }

    fun onBarcodeDetected(raw: String) {
        val now = System.currentTimeMillis()
        if (raw == lastScannedCode && (now - lastScanTimestamp) < 2000) {
            // Debounce rapid duplicates of same barcode
            return
        }
        if (_uiState.value.showConfirmSheet) {
            return
        }

        lastScannedCode = raw
        lastScanTimestamp = now

        // Parse: format could be "CODE" or "CODE|NAME|UOM"
        val code = if (raw.contains("|")) {
            raw.split("|")[0].trim()
        } else {
            raw.trim()
        }

        viewModelScope.launch {
            soundManager.playBeepAndVibrate()

            val found = materialRepository.getMaterialByCode(code)
            val material = found ?: MaterialEntity(
                code = code,
                name = if (raw.contains("|")) raw.split("|").getOrElse(1) { code }.trim() else code,
                uom = if (raw.contains("|")) raw.split("|").getOrElse(2) { "EA" }.trim() else "EA",
                stock = 0.0,
                price = 0.0,
                plant = "1304 HYDERABAD"
            )

            openConfirmSheet(material)
        }
    }

    private fun openConfirmSheet(material: MaterialEntity) {
        val initialQty = 1.0
        val isOverStock = mode == "ISSUE" && initialQty > material.stock

        _uiState.value = _uiState.value.copy(
            selectedMaterial = material,
            showConfirmSheet = true,
            issueQty = "1.0",
            requiredQty = "1.0",
            purpose = "Production",
            isOverStockWarning = isOverStock,
            receiveQty = "1.0",
            unitPrice = material.price.toString(),
            gstPct = "0.0", // 0% is valid and stays 0.0
            supplier = "",
            poNumber = "",
            challanNo = ""
        )
    }

    fun onIssueQtyChange(qtyStr: String) {
        val stock = _uiState.value.selectedMaterial?.stock ?: 0.0
        val qty = qtyStr.toDoubleOrNull() ?: 0.0
        val isOverStock = qty > stock

        _uiState.value = _uiState.value.copy(
            issueQty = qtyStr,
            isOverStockWarning = isOverStock
        )
    }

    fun onRequiredQtyChange(qtyStr: String) {
        _uiState.value = _uiState.value.copy(requiredQty = qtyStr)
    }

    fun onPurposeChange(purpose: String) {
        _uiState.value = _uiState.value.copy(purpose = purpose)
    }

    fun onReceiveQtyChange(qtyStr: String) {
        _uiState.value = _uiState.value.copy(receiveQty = qtyStr)
    }

    fun onUnitPriceChange(priceStr: String) {
        _uiState.value = _uiState.value.copy(unitPrice = priceStr)
    }

    fun onGstPctChange(gstStr: String) {
        _uiState.value = _uiState.value.copy(gstPct = gstStr)
    }

    fun onSupplierChange(s: String) {
        _uiState.value = _uiState.value.copy(supplier = s)
    }

    fun onPoNumberChange(s: String) {
        _uiState.value = _uiState.value.copy(poNumber = s)
    }

    fun onChallanNoChange(s: String) {
        _uiState.value = _uiState.value.copy(challanNo = s)
    }

    fun dismissConfirmSheet() {
        _uiState.value = _uiState.value.copy(showConfirmSheet = false)
    }

    fun confirmAdd(scanNext: Boolean, onDoneNavigateHome: () -> Unit) {
        val state = _uiState.value
        val material = state.selectedMaterial ?: return

        viewModelScope.launch {
            if (state.mode == "ISSUE") {
                val qty = state.issueQty.toDoubleOrNull() ?: 1.0
                val reqQty = state.requiredQty.toDoubleOrNull() ?: qty
                scanRepository.enqueueScan(
                    mode = "ISSUE",
                    materialCode = material.code,
                    materialName = material.name,
                    uom = material.uom,
                    qty = qty,
                    requiredQty = reqQty,
                    purpose = state.purpose.ifBlank { "Production" }
                )
            } else {
                val qty = state.receiveQty.toDoubleOrNull() ?: 1.0
                val price = state.unitPrice.toDoubleOrNull() ?: material.price
                val gst = state.gstPct.toDoubleOrNull() ?: 0.0 // 0% valid
                val totalPrice = qty * price * (1.0 + (gst / 100.0))

                scanRepository.enqueueScan(
                    mode = "RECEIVE",
                    materialCode = material.code,
                    materialName = material.name,
                    uom = material.uom,
                    qty = qty,
                    unitPrice = price,
                    gstPct = gst,
                    totalPrice = totalPrice,
                    supplier = state.supplier,
                    poNumber = state.poNumber,
                    challanNo = state.challanNo
                )
            }

            if (scanNext) {
                // Return immediately to camera
                _uiState.value = _uiState.value.copy(
                    showConfirmSheet = false,
                    selectedMaterial = null,
                    submissionMessage = "Scan enqueued!"
                )
            } else {
                _uiState.value = _uiState.value.copy(showConfirmSheet = false)
                onDoneNavigateHome()
            }
        }
    }
}
