package com.ttl.scanner.ui.history

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.ttl.scanner.data.local.ScanEventEntity
import com.ttl.scanner.ui.theme.*
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HistoryScreen(
    viewModel: HistoryViewModel,
    onNavigateBack: () -> Unit
) {
    val scans by viewModel.scans.collectAsState()
    val isRefreshing by viewModel.isRefreshing.collectAsState()

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Scan History", fontWeight = FontWeight.Bold) },
                navigationIcon = {
                    IconButton(onClick = onNavigateBack) {
                        Icon(Icons.Default.ArrowBack, contentDescription = "Back")
                    }
                },
                actions = {
                    IconButton(onClick = { viewModel.refresh() }) {
                        Icon(Icons.Default.Refresh, contentDescription = "Refresh")
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = Color.White)
            )
        }
    ) { paddingValues ->
        if (scans.isEmpty()) {
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(paddingValues),
                contentAlignment = Alignment.Center
            ) {
                Text("No scans recorded yet.", color = TextMuted, fontSize = 15.sp)
            }
        } else {
            LazyColumn(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(paddingValues)
                    .padding(horizontal = 16.dp, vertical = 8.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp)
            ) {
                items(scans, key = { it.eventId }) { scan ->
                    ScanHistoryCard(scan = scan)
                }
            }
        }
    }
}

@Composable
fun ScanHistoryCard(scan: ScanEventEntity) {
    val isIssue = scan.mode == "ISSUE"
    val modeColor = if (isIssue) IssueOrange else ReceiveBlue
    val timeStr = SimpleDateFormat("HH:mm:ss  dd-MMM", Locale.getDefault()).format(Date(scan.createdAt))

    Card(
        colors = CardDefaults.cardColors(containerColor = Color.White),
        elevation = CardDefaults.cardElevation(defaultElevation = 1.dp),
        shape = RoundedCornerShape(10.dp),
        modifier = Modifier.fillMaxWidth()
    ) {
        Column(modifier = Modifier.padding(14.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = scan.mode,
                    fontWeight = FontWeight.Black,
                    fontSize = 12.sp,
                    color = modeColor
                )
                StatusChip(status = scan.status)
            }

            Spacer(modifier = Modifier.height(6.dp))

            Text(
                text = scan.materialName,
                fontWeight = FontWeight.Bold,
                fontSize = 14.sp,
                color = TextDark
            )

            Spacer(modifier = Modifier.height(4.dp))

            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                Text("Code: ${scan.materialCode}", fontSize = 12.sp, color = TextMuted)
                Text("Qty: ${scan.qty} ${scan.uom}", fontSize = 13.sp, fontWeight = FontWeight.Bold, color = TextDark)
            }

            if (isIssue && !scan.purpose.isNullOrBlank()) {
                Spacer(modifier = Modifier.height(4.dp))
                Text("Purpose: ${scan.purpose}", fontSize = 12.sp, color = TextMuted)
            }

            if (!isIssue) {
                Spacer(modifier = Modifier.height(4.dp))
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween
                ) {
                    Text("GST: ${scan.gstPct ?: 0.0}%", fontSize = 12.sp, color = TextMuted)
                    if (scan.totalPrice != null) {
                        Text("Total: ₹${String.format(Locale.getDefault(), "%.2f", scan.totalPrice)}", fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
                    }
                }
            }

            // Display reject reason if rejected
            if (scan.status.equals("REJECTED", ignoreCase = true) && !scan.rejectReason.isNullOrBlank()) {
                Spacer(modifier = Modifier.height(6.dp))
                Text(
                    text = "Reason: ${scan.rejectReason}",
                    color = Color(0xFFDC2626),
                    fontSize = 12.sp,
                    fontWeight = FontWeight.Medium
                )
            }

            Spacer(modifier = Modifier.height(6.dp))
            Text(
                text = timeStr,
                fontSize = 11.sp,
                color = Color(0xFF94A3B8)
            )
        }
    }
}

@Composable
fun StatusChip(status: String) {
    val (bgColor, textColor, label) = when (status.uppercase()) {
        "APPLIED" -> Triple(Color(0xFFDCFCE7), Color(0xFF15803D), "Applied")
        "REJECTED" -> Triple(Color(0xFFFEE2E2), Color(0xFFB91C1C), "Rejected")
        "SENT" -> Triple(Color(0xFFFEF3C7), Color(0xFFB45309), "Sent (Waiting)")
        else -> Triple(Color(0xFFE0E7FF), Color(0xFF4338CA), "Queued (Offline)")
    }

    Box(
        modifier = Modifier
            .background(bgColor, RoundedCornerShape(12.dp))
            .padding(horizontal = 10.dp, vertical = 4.dp)
    ) {
        Text(
            text = label,
            color = textColor,
            fontSize = 11.sp,
            fontWeight = FontWeight.Bold
        )
    }
}
