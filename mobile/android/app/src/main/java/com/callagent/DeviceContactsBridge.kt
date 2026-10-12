package com.callagent

import android.content.ContentResolver
import android.content.Context
import android.database.Cursor
import android.provider.ContactsContract

data class DeviceContact(
    val name: String,
    val phoneNumber: String,
    val contactId: String? = null
)

/**
 * Device Contacts Bridge for Android.
 *
 * Interrogates Android ContactsContract to retrieve offline saved contacts.
 * Works completely offline without internet connectivity to enable local caller recognition.
 */
object DeviceContactsBridge {

    /**
     * Reads device contacts from Android ContentResolver.
     */
    fun fetchDeviceContacts(context: Context): List<DeviceContact> {
        val contactsList = mutableListOf<DeviceContact>()
        val contentResolver: ContentResolver = context.contentResolver

        val projection = arrayOf(
            ContactsContract.CommonDataKinds.Phone.CONTACT_ID,
            ContactsContract.CommonDataKinds.Phone.DISPLAY_NAME,
            ContactsContract.CommonDataKinds.Phone.NUMBER
        )

        val cursor: Cursor? = contentResolver.query(
            ContactsContract.CommonDataKinds.Phone.CONTENT_URI,
            projection,
            null,
            null,
            "${ContactsContract.CommonDataKinds.Phone.DISPLAY_NAME} ASC"
        )

        cursor?.use {
            val idIndex = it.getColumnIndex(ContactsContract.CommonDataKinds.Phone.CONTACT_ID)
            val nameIndex = it.getColumnIndex(ContactsContract.CommonDataKinds.Phone.DISPLAY_NAME)
            val numberIndex = it.getColumnIndex(ContactsContract.CommonDataKinds.Phone.NUMBER)

            while (it.moveToNext()) {
                val id = if (idIndex >= 0) it.getString(idIndex) else null
                val name = if (nameIndex >= 0) it.getString(nameIndex) else "Unknown Contact"
                val rawNumber = if (numberIndex >= 0) it.getString(numberIndex) else ""

                val normalized = NativeCallBridge.normalizePhoneNumber(rawNumber)
                if (NativeCallBridge.isValidPhoneNumber(normalized)) {
                    contactsList.add(
                        DeviceContact(
                            name = name,
                            phoneNumber = normalized,
                            contactId = id
                        )
                    )
                }
            }
        }

        return contactsList
    }
}
