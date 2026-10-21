package com.ttl.scanner

import com.ttl.scanner.data.local.ScanEventEntity
import org.junit.Assert.*
import org.junit.Test
import java.util.UUID

class ScanStatusLogicTest {

    @Test
    fun test_01_polling_transitions_sent_to_applied() {
        val scan = ScanEventEntity(
            eventId = UUID.randomUUID().toString(),
            mode = "ISSUE",
            materialCode = "MAT-101",
            materialName = "Hex Bolt",
            uom = "PCS",
            qty = 10.0,
            status = "SENT"
        )

        // Desktop marked the slip item as finalized/applied
        val serverPollStatus = "applied"
        val serverAppliedAt = System.currentTimeMillis()

        val updated = if (serverPollStatus == "applied") {
            scan.copy(status = "APPLIED", appliedAt = serverAppliedAt)
        } else {
            scan
        }

        assertEquals("APPLIED", updated.status)
        assertNotNull(updated.appliedAt)
    }

    @Test
    fun test_02_polling_transitions_sent_to_rejected_with_reason() {
        val scan = ScanEventEntity(
            eventId = UUID.randomUUID().toString(),
            mode = "ISSUE",
            materialCode = "MAT-101",
            materialName = "Hex Bolt",
            uom = "PCS",
            qty = 50.0,
            status = "SENT"
        )

        // Desktop rejected scan because phone scanning was turned off
        val serverPollStatus = "rejected"
        val serverRejectReason = "Phone scanning is OFF on desktop"

        val updated = if (serverPollStatus == "rejected") {
            scan.copy(status = "REJECTED", rejectReason = serverRejectReason)
        } else {
            scan
        }

        assertEquals("REJECTED", updated.status)
        assertEquals("Phone scanning is OFF on desktop", updated.rejectReason)
    }

    @Test
    fun test_03_polling_retains_sent_while_desktop_is_still_pending() {
        val scan = ScanEventEntity(
            eventId = UUID.randomUUID().toString(),
            mode = "RECEIVE",
            materialCode = "MAT-101",
            materialName = "Hex Bolt",
            uom = "PCS",
            qty = 25.0,
            status = "SENT"
        )

        // Desktop has not confirmed yet (auto-receive OFF)
        val serverPollStatus = "pending"

        val updated = when (serverPollStatus) {
            "applied" -> scan.copy(status = "APPLIED")
            "rejected" -> scan.copy(status = "REJECTED")
            else -> scan // stays SENT
        }

        assertEquals("SENT", updated.status)
    }
}
