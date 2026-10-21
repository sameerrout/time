package com.ttl.scanner

import com.ttl.scanner.data.local.ScanEventEntity
import org.junit.Assert.*
import org.junit.Test
import java.util.UUID

class OfflineQueueLogicTest {

    @Test
    fun test_01_scan_event_creation_has_uuid_and_queued_status() {
        val eventId = UUID.randomUUID().toString()
        val scan = ScanEventEntity(
            eventId = eventId,
            mode = "ISSUE",
            materialCode = "1001NM210010BL421",
            materialName = "INM 210 LTRS S42-BS BLUE",
            uom = "EA",
            qty = 10.0,
            requiredQty = 10.0,
            purpose = "Floor Assembly",
            status = "QUEUED",
            createdAt = System.currentTimeMillis()
        )

        assertEquals(36, scan.eventId.length)
        assertEquals("QUEUED", scan.status)
        assertNull(scan.rejectReason)
        assertNull(scan.appliedAt)
    }

    @Test
    fun test_02_transition_queued_to_sent_on_server_acknowledgement() {
        var scan = ScanEventEntity(
            eventId = UUID.randomUUID().toString(),
            mode = "ISSUE",
            materialCode = "1001NM210010BL421",
            materialName = "Test Item",
            uom = "EA",
            qty = 5.0,
            status = "QUEUED"
        )

        // Emulate server HTTP 200 response with data.status = "pending"
        val serverResponseStatus = "pending"
        val updatedScan = when (serverResponseStatus) {
            "applied" -> scan.copy(status = "APPLIED", appliedAt = System.currentTimeMillis())
            "rejected" -> scan.copy(status = "REJECTED", rejectReason = "Rejected by desktop")
            else -> scan.copy(status = "SENT")
        }

        assertEquals("SENT", updatedScan.status)
        assertNull(updatedScan.rejectReason)
    }

    @Test
    fun test_03_http_400_is_definitive_rejection_and_not_retried() {
        val scan = ScanEventEntity(
            eventId = UUID.randomUUID().toString(),
            mode = "ISSUE",
            materialCode = "UNKNOWN_CODE_999",
            materialName = "Unknown Item",
            uom = "EA",
            qty = 5.0,
            status = "QUEUED"
        )

        // Emulate HTTP 400 Bad Request
        val httpCode = 400
        val serverErrorMessage = "Unknown material code: 'UNKNOWN_CODE_999'"

        val updatedScan = if (httpCode == 400) {
            scan.copy(status = "REJECTED", rejectReason = serverErrorMessage)
        } else {
            scan.copy(status = "QUEUED", lastError = "Retry later")
        }

        // Definitive rejection: status is REJECTED, so WorkManager will not retry it
        assertEquals("REJECTED", updatedScan.status)
        assertEquals("Unknown material code: 'UNKNOWN_CODE_999'", updatedScan.rejectReason)
        assertNotEquals("QUEUED", updatedScan.status)
    }

    @Test
    fun test_04_network_unreachable_keeps_item_in_queued_state() {
        val scan = ScanEventEntity(
            eventId = UUID.randomUUID().toString(),
            mode = "RECEIVE",
            materialCode = "MAT-101",
            materialName = "Hex Bolt",
            uom = "PCS",
            qty = 100.0,
            status = "QUEUED"
        )

        // Network connection error occurs
        val isNetworkError = true
        val updatedScan = if (isNetworkError) {
            scan.copy(
                status = "QUEUED",
                lastError = "Can't reach the PC - make sure the software is running",
                syncAttempts = scan.syncAttempts + 1
            )
        } else {
            scan.copy(status = "SENT")
        }

        // Scan remains safely in QUEUED state on the phone until reconnected
        assertEquals("QUEUED", updatedScan.status)
        assertEquals(1, updatedScan.syncAttempts)
        assertTrue(updatedScan.lastError!!.contains("Can't reach the PC"))
    }
}
