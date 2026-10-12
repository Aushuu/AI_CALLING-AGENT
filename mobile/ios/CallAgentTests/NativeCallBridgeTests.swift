import XCTest
@testable import CallAgent

final class NativeCallBridgeTests: XCTestCase {

    func testNormalizePhoneNumber() {
        let bridge = NativeCallBridge.shared
        XCTAssertEqual(bridge.normalizePhoneNumber("+1 (555) 987-6543"), "+15559876543")
        XCTAssertEqual(bridge.normalizePhoneNumber("+91 99999-88888"), "+919999988888")
        XCTAssertEqual(bridge.normalizePhoneNumber("  1234567890  "), "1234567890")
    }

    func testIsValidPhoneNumber() {
        let bridge = NativeCallBridge.shared
        XCTAssertTrue(bridge.isValidPhoneNumber("+15551234567"))
        XCTAssertTrue(bridge.isValidPhoneNumber("1234567"))
        XCTAssertFalse(bridge.isValidPhoneNumber("1234"))
        XCTAssertFalse(bridge.isValidPhoneNumber("+1234567890123456"))
    }

    func testCreateCellularUrl() {
        let bridge = NativeCallBridge.shared
        let url = bridge.createCellularUrl(for: "+15551234567")
        XCTAssertNotNil(url)
        XCTAssertEqual(url?.scheme, "tel")
        XCTAssertEqual(url?.resourceSpecifier, "%2B15551234567")
    }
}
