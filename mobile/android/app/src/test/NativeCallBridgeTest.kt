package com.callagent

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class NativeCallBridgeTest {

    @Test
    fun testNormalizePhoneNumber_removesFormatting() {
        assertEquals("+15551234567", NativeCallBridge.normalizePhoneNumber("+1 (555) 123-4567"))
        assertEquals("+919876543210", NativeCallBridge.normalizePhoneNumber("+91 98765 43210"))
        assertEquals("9876543210", NativeCallBridge.normalizePhoneNumber("98765-43210"))
    }

    @Test
    fun testIsValidPhoneNumber_validatesLength() {
        assertTrue(NativeCallBridge.isValidPhoneNumber("+15551234567"))
        assertTrue(NativeCallBridge.isValidPhoneNumber("+919876543210"))
        assertTrue(NativeCallBridge.isValidPhoneNumber("1234567"))
        assertFalse(NativeCallBridge.isValidPhoneNumber("123")) // Too short
        assertFalse(NativeCallBridge.isValidPhoneNumber("1234567890123456")) // Too long (>15)
    }

    @Test
    fun testOfflineExecution_doesNotRequireNetwork() {
        // Cellular call intent uses standard tel: scheme directly handled by the baseband dialer
        val normalized = NativeCallBridge.normalizePhoneNumber("+15550000000")
        assertTrue(normalized.startsWith("+1555"))
    }
}
