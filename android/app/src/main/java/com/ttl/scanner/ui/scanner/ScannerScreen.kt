package com.ttl.scanner.ui.scanner

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.FlashOff
import androidx.compose.material.icons.filled.FlashOn
import androidx.compose.material.icons.filled.Search
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.ttl.scanner.ui.theme.IssueOrange
import com.ttl.scanner.ui.theme.ReceiveBlue
import com.ttl.scanner.ui.theme.TextMuted

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ScannerScreen(
    viewModel: ScannerViewModel,
    onNavigateBack: () -> Unit
) {
    val state by viewModel.uiState.collectAsState()
    val isIssueMode = state.mode == "ISSUE"
    val accentColor = if (isIssueMode) IssueOrange else ReceiveBlue

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Text(
                        text = if (isIssueMode) "Issue Slip Scanner" else "Purchase Order Scanner",
                        fontWeight = FontWeight.Bold,
                        fontSize = 18.sp
                    )
                },
                navigationIcon = {
                    IconButton(onClick = onNavigateBack) {
                        Icon(Icons.Default.ArrowBack, contentDescription = "Back")
                    }
                },
                actions = {
                    IconButton(onClick = { viewModel.toggleTorch() }) {
                        Icon(
                            if (state.isTorchOn) Icons.Default.FlashOn else Icons.Default.FlashOff,
                            contentDescription = "Torch",
                            tint = if (state.isTorchOn) Color(0xFFFACC15) else Color.DarkGray
                        )
                    }
                    IconButton(onClick = { viewModel.setSearchMode(true) }) {
                        Icon(Icons.Default.Search, contentDescription = "Manual Search")
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = Color.White)
            )
        }
    ) { paddingValues ->
        Box(
            modifier = Modifier
                .fillMaxSize()
                .padding(paddingValues)
        ) {
            // Live CameraX Preview
            CameraPreview(
                isTorchOn = state.isTorchOn,
                onBarcodeDetected = viewModel::onBarcodeDetected
            )

            // Viewfinder Reticle Box
            Box(
                modifier = Modifier
                    .size(280.dp, 200.dp)
                    .align(Alignment.Center)
                    .border(3.dp, accentColor, RoundedCornerShape(14.dp))
            )

            Text(
                text = "Align barcode or QR code within the frame",
                color = Color.White,
                fontSize = 13.sp,
                fontWeight = FontWeight.Medium,
                modifier = Modifier
                    .align(Alignment.Center)
                    .offset(y = 130.dp)
                    .background(Color(0x80000000), RoundedCornerShape(8.dp))
                    .padding(horizontal = 12.dp, vertical = 6.dp)
            )

            // Manual Material Search Overlay
            if (state.isSearchingManually) {
                Surface(
                    modifier = Modifier.fillMaxSize(),
                    color = Color.White
                ) {
                    Column(modifier = Modifier.fillMaxSize().padding(16.dp)) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            OutlinedTextField(
                                value = state.searchQuery,
                                onValueChange = viewModel::onSearchQueryChanged,
                                placeholder = { Text("Search material name or code...") },
                                modifier = Modifier.weight(1f),
                                singleLine = true,
                                shape = RoundedCornerShape(10.dp)
                            )
                            Spacer(modifier = Modifier.width(8.dp))
                            TextButton(onClick = { viewModel.setSearchMode(false) }) {
                                Text("Cancel")
                            }
                        }

                        Spacer(modifier = Modifier.height(12.dp))

                        LazyColumn(modifier = Modifier.fillMaxSize()) {
                            items(state.searchResults) { mat ->
                                Card(
                                    modifier = Modifier
                                        .fillMaxWidth()
                                        .padding(vertical = 4.dp)
                                        .clickable { viewModel.onMaterialSelected(mat) },
                                    colors = CardDefaults.cardColors(containerColor = Color(0xFFF8FAFC)),
                                    shape = RoundedCornerShape(8.dp)
                                ) {
                                    Column(modifier = Modifier.padding(12.dp)) {
                                        Text(mat.name, fontWeight = FontWeight.Bold, fontSize = 14.sp)
                                        Spacer(modifier = Modifier.height(4.dp))
                                        Row(
                                            horizontalArrangement = Arrangement.SpaceBetween,
                                            modifier = Modifier.fillMaxWidth()
                                        ) {
                                            Text("Code: ${mat.code}", fontSize = 12.sp, color = TextMuted)
                                            Text("Stock: ${mat.stock} ${mat.uom}", fontSize = 12.sp, fontWeight = FontWeight.SemiBold, color = accentColor)
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }

            // Confirmation Bottom Sheet
            if (state.showConfirmSheet && state.selectedMaterial != null) {
                val mat = state.selectedMaterial!!
                ModalBottomSheet(
                    onDismissRequest = viewModel::dismissConfirmSheet,
                    containerColor = Color.White
                ) {
                    Column(
                        modifier = Modifier
                            .fillMaxWidth()
                            .verticalScroll(rememberScrollState())
                            .padding(horizontal = 24.dp)
                            .padding(bottom = 32.dp)
                    ) {
                        Text(
                            text = if (isIssueMode) "Confirm Material Issue" else "Confirm Purchase Order Receipt",
                            style = MaterialTheme.typography.titleLarge,
                            fontWeight = FontWeight.Bold
                        )
                        Spacer(modifier = Modifier.height(12.dp))

                        // Material Info Box
                        Card(
                            colors = CardDefaults.cardColors(containerColor = Color(0xFFF1F5F9)),
                            shape = RoundedCornerShape(10.dp),
                            modifier = Modifier.fillMaxWidth()
                        ) {
                            Column(modifier = Modifier.padding(14.dp)) {
                                Text(mat.name, fontWeight = FontWeight.Bold, fontSize = 15.sp)
                                Spacer(modifier = Modifier.height(4.dp))
                                Row(
                                    horizontalArrangement = Arrangement.SpaceBetween,
                                    modifier = Modifier.fillMaxWidth()
                                ) {
                                    Text("Code: ${mat.code}", fontSize = 13.sp, color = TextMuted)
                                    Text("Current Stock: ${mat.stock} ${mat.uom}", fontSize = 13.sp, fontWeight = FontWeight.Bold, color = accentColor)
                                }
                            }
                        }

                        // Over-stock warning banner for ISSUE mode
                        if (isIssueMode && state.isOverStockWarning) {
                            Spacer(modifier = Modifier.height(10.dp))
                            Card(
                                colors = CardDefaults.cardColors(containerColor = Color(0xFFFEF2F2)),
                                shape = RoundedCornerShape(8.dp),
                                modifier = Modifier.fillMaxWidth()
                            ) {
                                Row(
                                    modifier = Modifier.padding(10.dp),
                                    verticalAlignment = Alignment.CenterVertically
                                ) {
                                    Icon(Icons.Default.Warning, contentDescription = null, tint = Color(0xFFDC2626), modifier = Modifier.size(20.dp))
                                    Spacer(modifier = Modifier.width(8.dp))
                                    Text(
                                        text = "Warning: Issued quantity (${state.issueQty}) exceeds available physical stock (${mat.stock})!",
                                        color = Color(0xFFB91C1C),
                                        fontSize = 12.sp,
                                        fontWeight = FontWeight.SemiBold
                                    )
                                }
                            }
                        }

                        Spacer(modifier = Modifier.height(14.dp))

                        if (isIssueMode) {
                            // ISSUE INPUTS
                            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                                OutlinedTextField(
                                    value = state.issueQty,
                                    onValueChange = viewModel::onIssueQtyChange,
                                    label = { Text("Quantity Issued") },
                                    modifier = Modifier.weight(1f),
                                    singleLine = true,
                                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                                    shape = RoundedCornerShape(8.dp)
                                )
                                OutlinedTextField(
                                    value = state.requiredQty,
                                    onValueChange = viewModel::onRequiredQtyChange,
                                    label = { Text("Required Qty") },
                                    modifier = Modifier.weight(1f),
                                    singleLine = true,
                                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                                    shape = RoundedCornerShape(8.dp)
                                )
                            }
                            Spacer(modifier = Modifier.height(10.dp))
                            OutlinedTextField(
                                value = state.purpose,
                                onValueChange = viewModel::onPurposeChange,
                                label = { Text("Purpose / Department (e.g. BM Production)") },
                                modifier = Modifier.fillMaxWidth(),
                                singleLine = true,
                                shape = RoundedCornerShape(8.dp)
                            )
                        } else {
                            // PURCHASE ORDER INPUTS
                            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                                OutlinedTextField(
                                    value = state.receiveQty,
                                    onValueChange = viewModel::onReceiveQtyChange,
                                    label = { Text("Quantity Received") },
                                    modifier = Modifier.weight(1f),
                                    singleLine = true,
                                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                                    shape = RoundedCornerShape(8.dp)
                                )
                                OutlinedTextField(
                                    value = state.unitPrice,
                                    onValueChange = viewModel::onUnitPriceChange,
                                    label = { Text("Unit Price (₹)") },
                                    modifier = Modifier.weight(1f),
                                    singleLine = true,
                                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                                    shape = RoundedCornerShape(8.dp)
                                )
                            }
                            Spacer(modifier = Modifier.height(10.dp))
                            OutlinedTextField(
                                value = state.gstPct,
                                onValueChange = viewModel::onGstPctChange,
                                label = { Text("GST % (0% is valid)") },
                                modifier = Modifier.fillMaxWidth(),
                                singleLine = true,
                                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                                shape = RoundedCornerShape(8.dp)
                            )
                            Spacer(modifier = Modifier.height(10.dp))
                            OutlinedTextField(
                                value = state.supplier,
                                onValueChange = viewModel::onSupplierChange,
                                label = { Text("Supplier Name") },
                                modifier = Modifier.fillMaxWidth(),
                                singleLine = true,
                                shape = RoundedCornerShape(8.dp)
                            )
                            Spacer(modifier = Modifier.height(10.dp))
                            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                                OutlinedTextField(
                                    value = state.poNumber,
                                    onValueChange = viewModel::onPoNumberChange,
                                    label = { Text("PO Number") },
                                    modifier = Modifier.weight(1f),
                                    singleLine = true,
                                    shape = RoundedCornerShape(8.dp)
                                )
                                OutlinedTextField(
                                    value = state.challanNo,
                                    onValueChange = viewModel::onChallanNoChange,
                                    label = { Text("Challan No") },
                                    modifier = Modifier.weight(1f),
                                    singleLine = true,
                                    shape = RoundedCornerShape(8.dp)
                                )
                            }
                        }

                        Spacer(modifier = Modifier.height(20.dp))

                        // Action Buttons: [ Add ] and [ Add & Scan Next ]
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.spacedBy(12.dp)
                        ) {
                            OutlinedButton(
                                onClick = { viewModel.confirmAdd(scanNext = false, onDoneNavigateHome = onNavigateBack) },
                                modifier = Modifier.weight(1f).height(50.dp),
                                shape = RoundedCornerShape(10.dp)
                            ) {
                                Text("Add", fontWeight = FontWeight.Bold, fontSize = 15.sp)
                            }

                            Button(
                                onClick = { viewModel.confirmAdd(scanNext = true, onDoneNavigateHome = onNavigateBack) },
                                modifier = Modifier.weight(1.3f).height(50.dp),
                                shape = RoundedCornerShape(10.dp),
                                colors = ButtonDefaults.buttonColors(containerColor = accentColor)
                            ) {
                                Text("Add & Scan Next", fontWeight = FontWeight.Bold, fontSize = 15.sp)
                            }
                        }
                    }
                }
            }
        }
    }
}
