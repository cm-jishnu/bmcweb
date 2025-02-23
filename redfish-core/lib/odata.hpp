// SPDX-License-Identifier: Apache-2.0
// SPDX-FileCopyrightText: Copyright OpenBMC Authors
#pragma once

#include "app.hpp"
#include "async_resp.hpp"
#include "http_request.hpp"
#include "http_response.hpp"

#include <boost/beast/http/verb.hpp>
#include <boost/url/format.hpp>
#include <boost/url/url.hpp>
#include <nlohmann/json.hpp>

#include <memory>
#include <ranges>
#include <string>
#include <string_view>
#include <utility>

namespace redfish
{

inline void redfishOdataGet(const crow::Request& /*req*/,
                            const std::shared_ptr<bmcweb::AsyncResp>& asyncResp)
{
    nlohmann::json::object_t obj;
    obj["@odata.context"] = "/redfish/v1/$metadata";
    nlohmann::json::array_t value;
    for (std::string_view service :
         {"$metadata", "odata", "JsonSchemas", "Service", "ServiceRoot",
          "Systems", "Chassis", "Managers", "SessionService", "AccountService",
          "UpdateService"})
    {
        nlohmann::json::object_t serviceObj;
        serviceObj["kind"] = "Singleton";
        serviceObj["name"] = "$metadata";
        boost::urls::url url = boost::urls::format("/redfish/v1/{}", service);
        if (service == "Service")
        {
            url = boost::urls::url("/redfish/v1");
        }
        serviceObj["url"] = url;
        value.emplace_back(std::move(serviceObj));
    }

    obj["value"] = std::move(value);

    asyncResp->res.jsonValue = std::move(obj);
}

inline void requestRoutesOdata(App& app)
{
    BMCWEB_ROUTE(app, "/redfish/v1/odata/")
        .methods(boost::beast::http::verb::get)(redfishOdataGet);
}

} // namespace redfish
