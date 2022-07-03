#include "utils/json_utils.hpp"

#include <string>
#include <vector>

#include <gmock/gmock.h>

namespace redfish::json_util
{
namespace
{

TEST(ReadJson, ValidElementsReturnsTrueResponseOkValuesUnpackedCorrectly)
{
    crow::Response res;
    nlohmann::json jsonRequest = {{"integer", 1},
                                  {"string", "hello"},
                                  {"vector", std::vector<uint64_t>{1, 2, 3}}};

    int64_t integer = 0;
    std::string str;
    std::vector<uint64_t> vec;
    EXPECT_TRUE(readJson(jsonRequest, res, "integer", integer, "string", str,
                         "vector", vec));
    EXPECT_EQ(res.result(), boost::beast::http::status::ok);
    EXPECT_TRUE(res.jsonValue.empty());

    EXPECT_EQ(integer, 1);
    EXPECT_EQ(str, "hello");
    EXPECT_TRUE((vec == std::vector<uint64_t>{1, 2, 3}));
}

TEST(readJson, ExtraElementsReturnsFalseReponseIsBadRequest)
{
    crow::Response res;
    nlohmann::json jsonRequest = {{"integer", 1}, {"string", "hello"}};

    std::optional<int> integer;
    std::optional<std::string> str;

    EXPECT_FALSE(readJson(jsonRequest, res, "integer", integer));
    EXPECT_EQ(res.result(), boost::beast::http::status::bad_request);
    EXPECT_FALSE(res.jsonValue.empty());
    EXPECT_EQ(integer, 1);

    EXPECT_FALSE(readJson(jsonRequest, res, "string", str));
    EXPECT_EQ(res.result(), boost::beast::http::status::bad_request);
    EXPECT_FALSE(res.jsonValue.empty());
    EXPECT_EQ(str, "hello");
}

TEST(ReadJson, WrongElementTypeReturnsFalseReponseIsBadRequest)
{
    crow::Response res;
    nlohmann::json jsonRequest = {{"integer", 1}, {"string0", "hello"}};

    int64_t integer = 0;
    std::string str0;
    EXPECT_FALSE(readJson(jsonRequest, res, "integer", str0));
    EXPECT_EQ(res.result(), boost::beast::http::status::bad_request);
    EXPECT_FALSE(res.jsonValue.empty());

    EXPECT_FALSE(readJson(jsonRequest, res, "string0", integer));
    EXPECT_EQ(res.result(), boost::beast::http::status::bad_request);
    EXPECT_FALSE(res.jsonValue.empty());

    EXPECT_FALSE(
        readJson(jsonRequest, res, "integer", str0, "string0", integer));
    EXPECT_EQ(res.result(), boost::beast::http::status::bad_request);
    EXPECT_FALSE(res.jsonValue.empty());
}

TEST(ReadJson, MissingElementReturnsFalseReponseIsBadRequest)
{
    crow::Response res;
    nlohmann::json jsonRequest = {{"integer", 1}, {"string0", "hello"}};

    int64_t integer = 0;
    std::string str0;
    std::string str1;
    std::vector<uint8_t> vec;
    EXPECT_FALSE(readJson(jsonRequest, res, "integer", integer, "string0", str0,
                          "vector", vec));
    EXPECT_EQ(res.result(), boost::beast::http::status::bad_request);
    EXPECT_FALSE(res.jsonValue.empty());

    EXPECT_FALSE(readJson(jsonRequest, res, "integer", integer, "string0", str0,
                          "string1", str1));
    EXPECT_EQ(res.result(), boost::beast::http::status::bad_request);
    EXPECT_FALSE(res.jsonValue.empty());
}

TEST(ReadJson, JsonArrayAreUnpackedCorrectly)
{
    crow::Response res;
    nlohmann::json jsonRequest = R"(
        {
            "TestJson": [{"hello": "yes"}, [{"there": "no"}, "nice"]]
        }
    )"_json;

    std::vector<nlohmann::json> jsonVec;
    EXPECT_TRUE(readJson(jsonRequest, res, "TestJson", jsonVec));
    EXPECT_EQ(res.result(), boost::beast::http::status::ok);
    EXPECT_TRUE(res.jsonValue.empty());
    EXPECT_EQ(jsonVec, R"([{"hello": "yes"}, [{"there": "no"}, "nice"]])"_json);
}

TEST(ReadJson, JsonSubElementValueAreUnpackedCorrectly)
{
    crow::Response res;
    nlohmann::json jsonRequest = R"(
        {
            "json": {"integer": 42}
        }
    )"_json;

    int integer = 0;
    EXPECT_TRUE(readJson(jsonRequest, res, "json/integer", integer));
    EXPECT_EQ(integer, 42);
    EXPECT_EQ(res.result(), boost::beast::http::status::ok);
    EXPECT_TRUE(res.jsonValue.empty());
}

TEST(ReadJson, JsonDeeperSubElementValueAreUnpackedCorrectly)
{
    crow::Response res;
    nlohmann::json jsonRequest = R"(
        {
            "json": {
                "json2": {"string": "foobar"}
            }
        }
    )"_json;

    std::string foobar;
    EXPECT_TRUE(readJson(jsonRequest, res, "json/json2/string", foobar));
    EXPECT_EQ(foobar, "foobar");
    EXPECT_EQ(res.result(), boost::beast::http::status::ok);
    EXPECT_TRUE(res.jsonValue.empty());
}

TEST(ReadJson, MultipleJsonSubElementValueAreUnpackedCorrectly)
{
    crow::Response res;
    nlohmann::json jsonRequest = R"(
        {
            "json": {
                "integer": 42,
                "string": "foobar"
            },
            "string": "bazbar"
        }
    )"_json;

    int integer = 0;
    std::string foobar;
    std::string bazbar;
    EXPECT_TRUE(readJson(jsonRequest, res, "json/integer", integer,
                         "json/string", foobar, "string", bazbar));
    EXPECT_EQ(integer, 42);
    EXPECT_EQ(foobar, "foobar");
    EXPECT_EQ(bazbar, "bazbar");
    EXPECT_EQ(res.result(), boost::beast::http::status::ok);
    EXPECT_TRUE(res.jsonValue.empty());
}

TEST(ReadJson, ExtraElement)
{
    crow::Response res;
    nlohmann::json jsonRequest = {{"integer", 1}, {"string", "hello"}};

    std::optional<int> integer;
    std::optional<std::string> str;

    EXPECT_FALSE(readJson(jsonRequest, res, "integer", integer));
    EXPECT_EQ(res.result(), boost::beast::http::status::bad_request);
    EXPECT_FALSE(res.jsonValue.empty());
    EXPECT_EQ(integer, 1);

    EXPECT_FALSE(readJson(jsonRequest, res, "string", str));
    EXPECT_EQ(res.result(), boost::beast::http::status::bad_request);
    EXPECT_FALSE(res.jsonValue.empty());
    EXPECT_EQ(str, "hello");
}

TEST(ReadJson, ValidMissingElementReturnsTrue)
{
    crow::Response res;
    nlohmann::json jsonRequest = {{"integer", 1}};

    std::optional<int> integer;
    int requiredInteger = 0;
    std::optional<std::string> str0;
    std::optional<std::string> str1;
    std::optional<std::vector<uint8_t>> vec;
    EXPECT_TRUE(readJson(jsonRequest, res, "missing_integer", integer,
                         "integer", requiredInteger));
    EXPECT_EQ(res.result(), boost::beast::http::status::ok);
    EXPECT_TRUE(res.jsonValue.empty());
    EXPECT_EQ(integer, std::nullopt);

    EXPECT_TRUE(readJson(jsonRequest, res, "missing_string", str0, "integer",
                         requiredInteger));
    EXPECT_EQ(res.result(), boost::beast::http::status::ok);
    EXPECT_TRUE(res.jsonValue.empty());
    EXPECT_EQ(str0, std::nullopt);

    EXPECT_TRUE(readJson(jsonRequest, res, "integer", integer, "string", str0,
                         "vector", vec));
    EXPECT_EQ(res.result(), boost::beast::http::status::ok);
    EXPECT_TRUE(res.jsonValue.empty());
    EXPECT_EQ(integer, 1);
    EXPECT_EQ(str0, std::nullopt);
    EXPECT_EQ(vec, std::nullopt);

    EXPECT_TRUE(readJson(jsonRequest, res, "integer", integer, "string0", str0,
                         "missing_string", str1));
    EXPECT_EQ(res.result(), boost::beast::http::status::ok);
    EXPECT_TRUE(res.jsonValue.empty());
    EXPECT_EQ(str1, std::nullopt);
}

TEST(ReadJson, InvalidMissingElementReturnsFalse)
{
    crow::Response res;
    nlohmann::json jsonRequest = {{"integer", 1}, {"string", "hello"}};

    int integer = 0;
    std::string str0;
    std::string str1;
    std::vector<uint8_t> vec;
    EXPECT_FALSE(readJson(jsonRequest, res, "missing_integer", integer));
    EXPECT_EQ(res.result(), boost::beast::http::status::bad_request);
    EXPECT_FALSE(res.jsonValue.empty());

    EXPECT_FALSE(readJson(jsonRequest, res, "missing_string", str0));
    EXPECT_EQ(res.result(), boost::beast::http::status::bad_request);
    EXPECT_FALSE(res.jsonValue.empty());

    EXPECT_FALSE(readJson(jsonRequest, res, "integer", integer, "string", str0,
                          "vector", vec));
    EXPECT_EQ(res.result(), boost::beast::http::status::bad_request);
    EXPECT_FALSE(res.jsonValue.empty());

    EXPECT_FALSE(readJson(jsonRequest, res, "integer", integer, "string0", str0,
                          "missing_string", str1));
    EXPECT_EQ(res.result(), boost::beast::http::status::bad_request);
    EXPECT_FALSE(res.jsonValue.empty());
}

TEST(ReadJsonPatch, ValidElementsReturnsTrueResponseOkValuesUnpackedCorrectly)
{
    crow::Response res;
    std::error_code ec;
    crow::Request req({}, ec);
    // Ignore errors intentionally
    req.body = "{\"integer\": 1}";

    int64_t integer = 0;
    EXPECT_TRUE(readJsonPatch(req, res, "integer", integer));
    EXPECT_EQ(res.result(), boost::beast::http::status::ok);
    EXPECT_TRUE(res.jsonValue.empty());
}

TEST(ReadJsonPatch, EmptyObjectReturnsFalseResponseBadRequest)
{
    crow::Response res;
    std::error_code ec;
    crow::Request req({}, ec);
    // Ignore errors intentionally
    req.body = "{}";

    std::optional<int64_t> integer = 0;
    EXPECT_FALSE(readJsonPatch(req, res, "integer", integer));
    EXPECT_EQ(res.result(), boost::beast::http::status::bad_request);
    EXPECT_FALSE(res.jsonValue.empty());
}

TEST(ReadJsonPatch, OdataIgnored)
{
    crow::Response res;
    std::error_code ec;
    crow::Request req({}, ec);
    // Ignore errors intentionally
    req.body = R"({"@odata.etag": "etag", "integer": 1})";

    std::optional<int64_t> integer = 0;
    EXPECT_TRUE(readJsonPatch(req, res, "integer", integer));
    EXPECT_EQ(res.result(), boost::beast::http::status::ok);
    EXPECT_TRUE(res.jsonValue.empty());
}

TEST(ReadJsonPatch, OnlyOdataGivesNoOperation)
{
    crow::Response res;
    std::error_code ec;
    crow::Request req({}, ec);
    // Ignore errors intentionally
    req.body = R"({"@odata.etag": "etag"})";

    std::optional<int64_t> integer = 0;
    EXPECT_FALSE(readJsonPatch(req, res, "integer", integer));
    EXPECT_EQ(res.result(), boost::beast::http::status::bad_request);
    EXPECT_FALSE(res.jsonValue.empty());
}

TEST(ReadJsonAction, ValidElementsReturnsTrueResponseOkValuesUnpackedCorrectly)
{
    crow::Response res;
    std::error_code ec;
    crow::Request req({}, ec);
    // Ignore errors intentionally
    req.body = "{\"integer\": 1}";

    int64_t integer = 0;
    EXPECT_TRUE(readJsonAction(req, res, "integer", integer));
    EXPECT_EQ(res.result(), boost::beast::http::status::ok);
    EXPECT_TRUE(res.jsonValue.empty());
    EXPECT_EQ(integer, 1);
}

TEST(ReadJsonAction, EmptyObjectReturnsTrueResponseOk)
{
    crow::Response res;
    std::error_code ec;
    crow::Request req({}, ec);
    // Ignore errors intentionally
    req.body = "{}";

    std::optional<int64_t> integer = 0;
    EXPECT_TRUE(readJsonAction(req, res, "integer", integer));
    EXPECT_EQ(res.result(), boost::beast::http::status::ok);
    EXPECT_TRUE(res.jsonValue.empty());
}

} // namespace
} // namespace redfish::json_util