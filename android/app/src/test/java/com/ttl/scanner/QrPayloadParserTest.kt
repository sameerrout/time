package com.ttl.scanner

import com.ttl.scanner.util.QrPayloadParser
import org.junit.Assert.*
import org.junit.Test

class QrPayloadParserTest {

    @Test
    fun test_01_parse_compact_json_pairing_payload() {
        val jsonText = """{"v":1,"url":"https://orange-mango-banana.trycloudflare.com","id":"bf66a7e1-5e7a-43af-afc4-3124632388a2","code":"482910"}"""
        val parsed = QrPayloadParser.parse(jsonText)

        assertNotNull("Payload should be parsed", parsed)
        assertEquals("https://orange-mango-banana.trycloudflare.com", parsed?.url)
        assertEquals("bf66a7e1-5e7a-43af-afc4-3124632388a2", parsed?.installationId)
        assertEquals("482910", parsed?.code)
        assertFalse("Should not be address-only update", parsed?.isAddressOnlyUpdate == true)
    }

    @Test
    fun test_02_parse_compact_json_address_only_update() {
        val jsonText = """{"v":1,"url":"https://new-address-after-restart.trycloudflare.com","id":"bf66a7e1-5e7a-43af-afc4-3124632388a2","code":""}"""
        val parsed = QrPayloadParser.parse(jsonText)

        assertNotNull(parsed)
        assertEquals("https://new-address-after-restart.trycloudflare.com", parsed?.url)
        assertEquals("bf66a7e1-5e7a-43af-afc4-3124632388a2", parsed?.installationId)
        assertNull("Empty code should parse to null", parsed?.code)
        assertTrue("Should be flagged as address-only update", parsed?.isAddressOnlyUpdate == true)
    }

    @Test
    fun test_03_parse_query_param_url() {
        val uriText = "https://192.168.100.121:8443/?code=782617"
        val parsed = QrPayloadParser.parse(uriText)

        assertNotNull(parsed)
        assertEquals("https://192.168.100.121:8443", parsed?.url)
        assertEquals("782617", parsed?.code)
        assertFalse(parsed?.isAddressOnlyUpdate == true)
    }

    @Test
    fun test_04_parse_plain_url_without_code() {
        val urlText = "https://192.168.100.121:8443"
        val parsed = QrPayloadParser.parse(urlText)

        assertNotNull(parsed)
        assertEquals("https://192.168.100.121:8443", parsed?.url)
        assertNull(parsed?.code)
        assertTrue(parsed?.isAddressOnlyUpdate == true)
    }

    @Test
    fun test_05_invalid_text_returns_null() {
        assertNull(QrPayloadParser.parse(null))
        assertNull(QrPayloadParser.parse(""))
        assertNull(QrPayloadParser.parse("   "))
        assertNull(QrPayloadParser.parse("random unformatted text"))
    }
}
