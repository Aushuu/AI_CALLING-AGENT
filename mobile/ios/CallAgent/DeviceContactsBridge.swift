import Foundation
import Contacts

public struct IOSDeviceContact {
    public let identifier: String
    public let fullName: String
    public let phoneNumbers: [String]

    public init(identifier: String, fullName: String, phoneNumbers: [String]) {
        self.identifier = identifier
        self.fullName = fullName
        self.phoneNumbers = phoneNumbers
    }
}

/**
 * Device Contacts Bridge for iOS.
 *
 * Interacts with iOS Contacts framework (CNContactStore) to fetch device contacts
 * completely offline for immediate caller recognition and personalized rules.
 */
public final class DeviceContactsBridge {

    public static let shared = DeviceContactsBridge()
    private let contactStore = CNContactStore()

    private init() {}

    /**
     * Request access to the user's contacts.
     */
    public func requestContactsAccess() async -> Bool {
        do {
            return try await contactStore.requestAccess(for: .contacts)
        } catch {
            return false
        }
    }

    /**
     * Fetch device contacts completely offline.
     */
    public func fetchContacts() throws -> [IOSDeviceContact] {
        let keysToFetch: [CNKeyDescriptor] = [
            CNContactIdentifierKey as CNKeyDescriptor,
            CNContactGivenNameKey as CNKeyDescriptor,
            CNContactFamilyNameKey as CNKeyDescriptor,
            CNContactPhoneNumbersKey as CNKeyDescriptor
        ]

        let request = CNContactFetchRequest(keysToFetch: keysToFetch)
        var results: [IOSDeviceContact] = []

        try contactStore.enumerateContacts(with: request) { contact, _ in
            let fullName = "\(contact.givenName) \(contact.familyName)".trimmingCharacters(in: .whitespaces)
            let phoneNumbers = contact.phoneNumbers.map { phone in
                NativeCallBridge.shared.normalizePhoneNumber(phone.value.stringValue)
            }.filter { NativeCallBridge.shared.isValidPhoneNumber($0) }

            if !phoneNumbers.isEmpty {
                results.append(
                    IOSDeviceContact(
                        identifier: contact.identifier,
                        fullName: fullName.isEmpty ? "Unknown" : fullName,
                        phoneNumbers: phoneNumbers
                    )
                )
            }
        }

        return results
    }
}
