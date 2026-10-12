import Foundation
import UIKit
import CoreTelephony

/**
 * Native Cellular Calling Bridge for iOS.
 *
 * Initiates standard cellular calls via `tel://` URL scheme, invoking the native iOS
 * Phone app without requiring internet connectivity. Cellular traffic is handled directly
 * by the device's SIM card and carrier baseband.
 */
public final class NativeCallBridge {

    public static let shared = NativeCallBridge()

    private init() {}

    /**
     * Sanitizes and normalizes phone numbers into E.164 compatible format.
     */
    public func normalizePhoneNumber(_ rawNumber: String) -> String {
        let trimmed = rawNumber.trimmingCharacters(in: .whitespacesAndNewlines)
        let hasPlus = trimmed.hasPrefix("+")
        let digitsOnly = trimmed.filter { $0.isNumber }
        return hasPlus ? "+\(digitsOnly)" : String(digitsOnly)
    }

    /**
     * Validates that the phone number contains between 7 and 15 digits.
     */
    public func isValidPhoneNumber(_ number: String) -> Bool {
        let digits = number.filter { $0.isNumber }
        return digits.count >= 7 && digits.count <= 15
    }

    /**
     * Creates a cellular telephone URL with the standard `tel:` scheme.
     */
    public func createCellularUrl(for phoneNumber: String) -> URL? {
        let normalized = normalizePhoneNumber(phoneNumber)
        guard isValidPhoneNumber(normalized) else { return nil }
        guard let encoded = normalized.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) else {
            return nil
        }
        return URL(string: "tel:\(encoded)")
    }

    /**
     * Initiates the native cellular phone call using UIApplication.
     * Internet connectivity is NOT required.
     */
    @MainActor
    public func startCellularCall(to phoneNumber: String, completion: ((Bool) -> Void)? = nil) {
        guard let url = createCellularUrl(for: phoneNumber) else {
            completion?(false)
            return
        }

        if UIApplication.shared.canOpenURL(url) {
            UIApplication.shared.open(url, options: [:]) { success in
                completion?(success)
            }
        } else {
            completion?(false)
        }
    }
}
