package com.callagent

import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.telecom.TelecomManager
import androidx.core.content.ContextCompat

/**
 * Native Cellular Calling Bridge for Android.
 *
 * Initiates standard cellular phone calls using the device's native telephony system.
 * Internet connectivity is strictly NOT required for actual cellular calling, as calls
 * are routed directly through the carrier baseband modem and public switched telephone network (PSTN).
 */
object NativeCallBridge {

    /**
     * Sanitizes and normalizes phone numbers into E.164 compatible format.
     */
    fun normalizePhoneNumber(rawNumber: String): String {
        val trimmed = rawNumber.trim()
        val hasLeadingPlus = trimmed.startsWith("+")
        val digitsOnly = trimmed.filter { it.isDigit() }
        return if (hasLeadingPlus) "+$digitsOnly" else digitsOnly
    }

    /**
     * Validates that the number has a valid digit length (7 to 15 digits).
     */
    fun isValidPhoneNumber(number: String): Boolean {
        val digits = number.filter { it.isDigit() }
        return digits.length in 7..15
    }

    /**
     * Checks whether the host device possesses native cellular telephony capability.
     */
    fun canPlaceCellularCall(context: Context): Boolean {
        val packageManager = context.packageManager
        return packageManager.hasSystemFeature(PackageManager.FEATURE_TELEPHONY)
    }

    /**
     * Creates an Intent to initiate a native cellular call.
     *
     * @param context Android context
     * @param phoneNumber Destination phone number
     * @param directCall If true and CALL_PHONE permission is granted, initiates call immediately;
     *                   otherwise, opens the native dialer pre-populated with the number.
     * @return Intent ready to be started via context.startActivity(intent)
     */
    fun createCallIntent(context: Context, phoneNumber: String, directCall: Boolean = false): Intent {
        val normalized = normalizePhoneNumber(phoneNumber)
        require(isValidPhoneNumber(normalized)) { "Invalid phone number format: $phoneNumber" }

        val uri = Uri.parse("tel:${Uri.encode(normalized)}")
        val hasCallPermission = ContextCompat.checkSelfPermission(
            context,
            android.Manifest.permission.CALL_PHONE
        ) == PackageManager.PERMISSION_GRANTED

        val action = if (directCall && hasCallPermission) {
            Intent.ACTION_CALL
        } else {
            Intent.ACTION_DIAL
        }

        return Intent(action, uri).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK
        }
    }

    /**
     * Initiates the cellular call directly from the app context without requiring internet.
     */
    fun startCellularCall(context: Context, phoneNumber: String, directCall: Boolean = false): Boolean {
        return try {
            val intent = createCallIntent(context, phoneNumber, directCall)
            context.startActivity(intent)
            true
        } catch (e: Exception) {
            false
        }
    }
}
