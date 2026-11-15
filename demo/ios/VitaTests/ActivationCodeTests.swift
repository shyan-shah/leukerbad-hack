import XCTest
@testable import Vita

final class ActivationCodeTests: XCTestCase {
    func testAcceptsTheThreeStickerFormats() {
        let want = ActivationCode(robot: "R-01", code: "8F3K2Q")
        XCTAssertEqual(ActivationCode.parse("vita://activate?robot=R-01&code=8F3K2Q"), want)
        XCTAssertEqual(ActivationCode.parse("https://vita.example/activate?robot=r-01&code=8F3K2Q"), want)
        XCTAssertEqual(ActivationCode.parse("  VITA:R-01:8F3K2Q\n"), want)
    }

    func testRejectsAnythingElse() {
        XCTAssertNil(ActivationCode.parse("https://example.com"))
        XCTAssertNil(ActivationCode.parse("VITA:R-01"))
        XCTAssertNil(ActivationCode.parse("VITA:R-01/../admin:8F3K2Q"))
        XCTAssertNil(ActivationCode.parse("http://evil.example/activate?robot=R-01&code=8F3K2Q"))
        XCTAssertNil(ActivationCode.parse("VITA:R-01:ab"))
    }

    func testServerAddressMustNotSendTheKeyInTheClear() throws {
        XCTAssertNoThrow(try APIClient.check("https://api.example.com"))
        XCTAssertNoThrow(try APIClient.check("http://192.168.1.20:8080"))
        XCTAssertNoThrow(try APIClient.check("http://vita-arm.local"))
        XCTAssertThrowsError(try APIClient.check("http://api.example.com"))
        XCTAssertThrowsError(try APIClient.check("ftp://192.168.1.20"))
    }
}
