document.addEventListener("DOMContentLoaded", function () {
  /* ---------- Global hamburger drawer ---------- */
  var burger = document.querySelector("[data-gnav-toggle]");
  var drawer = document.getElementById("global-drawer");
  var overlay = document.querySelector("[data-gnav-overlay]");
  var closeBtn = drawer ? drawer.querySelector("[data-gnav-close]") : null;
  if (burger && drawer && overlay) {
    var openLabel = burger.getAttribute("aria-label") || "Open navigation menu";
    var closeLabel = (closeBtn && closeBtn.getAttribute("aria-label")) || "Close navigation menu";
    var lastFocus = null;

    function openDrawer() {
      lastFocus = document.activeElement;
      drawer.hidden = false;
      overlay.hidden = false;
      /* force reflow so the slide-in transition plays */
      void drawer.offsetWidth;
      drawer.classList.remove("gnav-closed");
      document.body.classList.add("gnav-open");
      burger.setAttribute("aria-expanded", "true");
      burger.setAttribute("aria-label", closeLabel);
      if (closeBtn) closeBtn.focus();
    }
    function closeDrawer() {
      drawer.classList.add("gnav-closed");
      document.body.classList.remove("gnav-open");
      burger.setAttribute("aria-expanded", "false");
      burger.setAttribute("aria-label", openLabel);
      window.setTimeout(function () {
        drawer.hidden = true;
        overlay.hidden = true;
      }, 200);
      if (lastFocus && lastFocus.focus) lastFocus.focus();
      else burger.focus();
    }
    function isOpen() {
      return burger.getAttribute("aria-expanded") === "true";
    }
    drawer.classList.add("gnav-closed");
    burger.addEventListener("click", function () {
      if (isOpen()) closeDrawer();
      else openDrawer();
    });
    if (closeBtn) closeBtn.addEventListener("click", closeDrawer);
    overlay.addEventListener("click", closeDrawer);
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && isOpen()) closeDrawer();
    });
    drawer.querySelectorAll("a").forEach(function (link) {
      link.addEventListener("click", closeDrawer);
    });
  }

  document.querySelectorAll("[data-evidence-controls]").forEach(function (controls) {
    var inputs = controls.querySelectorAll("[data-evidence-input]");
    var triggers = controls.querySelectorAll("[data-evidence-trigger]");
    var clearButton = controls.querySelector("[data-clear-evidence]");
    var nameEl = controls.parentElement.querySelector("[data-evidence-name]");
    var emptyText = nameEl ? nameEl.textContent : "";

    triggers.forEach(function (trigger) {
      trigger.addEventListener("click", function () {
        var input = document.getElementById(trigger.dataset.evidenceTrigger);
        if (input) input.click();
      });
    });

    inputs.forEach(function (input) {
      input.addEventListener("change", function () {
        inputs.forEach(function (otherInput) {
          if (otherInput !== input) otherInput.value = "";
        });
        if (input.files && input.files.length > 0) {
          if (nameEl) nameEl.textContent = "Selected: " + input.files[0].name;
          if (clearButton) clearButton.hidden = false;
        }
      });
    });

    if (clearButton) {
      clearButton.addEventListener("click", function () {
        inputs.forEach(function (input) { input.value = ""; });
        if (nameEl) nameEl.textContent = emptyText;
        clearButton.hidden = true;
      });
    }
  });

  document.querySelectorAll("[data-location-picker]").forEach(function (picker) {
    var mapEl = picker.querySelector("[data-location-map]");
    var statusEl = picker.querySelector("[data-location-status]");
    var useLocationButton = picker.querySelector("[data-use-location]");
    var searchInput = picker.querySelector("[data-location-search]");
    var searchButton = picker.querySelector("[data-search-location]");
    var suggestionsEl = picker.querySelector("[data-location-suggestions]");
    var searchStatus = picker.querySelector("[data-location-search-status]");
    function pick(sel) {
      return picker.querySelector(sel) || document.querySelector(sel);
    }
    var latitudeInput = pick("[data-latitude]");
    var longitudeInput = pick("[data-longitude]");
    var addressInput = pick("[data-location-address]");
    var cityInput = pick("[data-location-city]");
    var stateInput = pick("[data-location-state]");
    var pincodeInput = pick("[data-location-pincode]");
    var locationTextInput = document.querySelector("#location_text");
    var districtInput = document.querySelector("#district");
    if (!mapEl) return;

    var map = null;
    if (window.L) {
      /* India-wide default view (was Jharkhand-only). */
      map = L.map(mapEl).setView([23.5, 80.5], 5);
      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        attribution: "&copy; OpenStreetMap contributors",
        maxZoom: 19
      }).addTo(map);
      window.setTimeout(function () { map.invalidateSize(); }, 150);
    } else if (statusEl) {
      statusEl.textContent = "Map library could not load. You can still type the address and district manually.";
    }
    var marker;

    function showMapLocation(latitude, longitude) {
      if (!map) return;
      if (marker) marker.setLatLng([latitude, longitude]);
      else marker = L.marker([latitude, longitude]).addTo(map);
      map.setView([latitude, longitude], 15);
    }

    function applyDistrict(value) {
      if (!districtInput || !value) return;
      var normalized = value.replace(/\s+district$/i, "").trim();
      if (!normalized) return;
      if (districtInput.tagName === "SELECT") {
        var low = normalized.toLowerCase();
        Array.prototype.forEach.call(districtInput.options, function (option) {
          if (option.value.toLowerCase() === low || option.textContent.toLowerCase() === low) {
            districtInput.value = option.value;
          }
        });
      } else {
        /* Free-text district (all-India): take the reverse-geocoded
           district as the current location's district. */
        districtInput.value = normalized.charAt(0).toUpperCase() + normalized.slice(1);
        districtInput.dispatchEvent(new Event("input", { bubbles: true }));
      }
    }

    function reverseGeocode(latitude, longitude) {
      var endpoint = "https://nominatim.openstreetmap.org/reverse?format=jsonv2&addressdetails=1&lat=" +
        encodeURIComponent(latitude) + "&lon=" + encodeURIComponent(longitude);
      fetch(endpoint, { headers: { Accept: "application/json" } })
        .then(function (response) {
          if (!response.ok) throw new Error("Reverse geocoding failed");
          return response.json();
        })
        .then(function (data) {
          var address = data.address || {};
          var city = address.city || address.town || address.village || address.municipality || "";
          var district = address.state_district || address.county || "";
          if (addressInput) addressInput.value = data.display_name || "";
          if (cityInput) cityInput.value = city;
          if (stateInput) {
            stateInput.value = address.state || "";
            stateInput.dispatchEvent(new Event("input", { bubbles: true }));
          }
          if (pincodeInput) pincodeInput.value = address.postcode || "";
          if (locationTextInput && !locationTextInput.value) locationTextInput.value = data.display_name || "";
          applyDistrict(district);
          statusEl.textContent = "Location details filled. You can edit them if needed.";
          /* Nominatim often omits the postcode — second provider fills it. */
          if (!address.postcode) fillPincodeFallback(latitude, longitude);
        })
        .catch(function () {
          /* Nominatim down: try the fallback provider before giving up. */
          fillPincodeFallback(latitude, longitude, true);
        });
    }

    /* BigDataCloud free reverse-geocode (no key): supplies missing
       pincode/city/state when Nominatim lacks them or is unreachable. */
    function fillPincodeFallback(latitude, longitude, full) {
      var url = "https://api.bigdatacloud.net/data/reverse-geocode-client?latitude=" +
        encodeURIComponent(latitude) + "&longitude=" + encodeURIComponent(longitude) +
        "&localityLanguage=en";
      fetch(url, { headers: { Accept: "application/json" } })
        .then(function (response) {
          if (!response.ok) throw new Error("fallback geocode failed");
          return response.json();
        })
        .then(function (data) {
          data = data || {};
          if (pincodeInput && !pincodeInput.value && data.postcode) {
            pincodeInput.value = data.postcode;
          }
          if (stateInput && !stateInput.value && data.principalSubdivision) {
            stateInput.value = data.principalSubdivision;
            stateInput.dispatchEvent(new Event("input", { bubbles: true }));
          }
          if (cityInput && !cityInput.value && (data.city || data.locality)) {
            cityInput.value = data.city || data.locality;
          }
          if (full) {
            if (locationTextInput && !locationTextInput.value && data.locality) {
              locationTextInput.value = [data.locality, data.city,
                data.principalSubdivision].filter(Boolean).join(", ");
            }
            applyDistrict(data.city || data.locality || "");
            statusEl.textContent = "Location details filled. You can edit them if needed.";
          }
        })
        .catch(function () {
          if (full) {
            statusEl.textContent = "Location selected. Please check or complete the address details.";
          }
        });
    }

    function setLocation(latitude, longitude, message) {
      if (latitudeInput) latitudeInput.value = latitude.toFixed(6);
      if (longitudeInput) longitudeInput.value = longitude.toFixed(6);
      showMapLocation(latitude, longitude);
      if (statusEl) statusEl.textContent = message;
      var readout = picker.querySelector("[data-location-readout]");
      if (readout) {
        readout.textContent = "Selected Location: " + latitude.toFixed(6) +
          ", " + longitude.toFixed(6);
      }
      reverseGeocode(latitude, longitude);
    }

    if (map) {
      map.on("click", function (event) {
        setLocation(event.latlng.lat, event.latlng.lng, "Location selected on the map.");
      });
    }

    function searchLocation() {
      var query = searchInput ? searchInput.value.trim() : "";
      if (!query) {
        if (searchStatus) searchStatus.textContent = "Enter an area, landmark, or address first.";
        return;
      }
      if (searchStatus) searchStatus.textContent = "Searching...";
      var endpoints = [
        "https://nominatim.openstreetmap.org/search?format=jsonv2&addressdetails=1&countrycodes=in&limit=1&q=" +
          encodeURIComponent(query),
        "https://photon.komoot.io/api/?limit=1&lang=en&q=" + encodeURIComponent(query)
      ];
      /* Pure pincode queries go to the postal-code endpoint first, which
         resolves far more pincodes than text search. */
      if (/^\d{6}$/.test(query.replace(/\s+/g, ""))) {
        endpoints.unshift(
          "https://nominatim.openstreetmap.org/search?format=jsonv2&addressdetails=1&countrycodes=in&limit=1&postalcode=" +
          encodeURIComponent(query.replace(/\s+/g, "")));
      }

      function requestSearch(index) {
        return fetch(endpoints[index], { headers: { Accept: "application/json" } })
          .then(function (response) {
            if (!response.ok) throw new Error("Location search failed");
            return response.json();
          })
          .then(function (data) {
            var results = index === 0 ? data : (data.features || []).map(function (feature) {
              var coordinates = feature.geometry && feature.geometry.coordinates;
              return coordinates ? { lat: coordinates[1], lon: coordinates[0] } : null;
            }).filter(Boolean);
            if (!results.length) throw new Error("Location not found");
            return results[0];
          })
          .catch(function (error) {
            if (index + 1 < endpoints.length) return requestSearch(index + 1);
            throw error;
          });
      }

      requestSearch(0)
        .then(function (result) {
          selectSearchResult(result);
        })
        .catch(function () {
          if (searchStatus) searchStatus.textContent = "Location not found. Try a nearby landmark or address.";
        });
    }

    function clearSearchLocation() {
      if (searchInput) searchInput.value = "";
      if (suggestionsEl) {
        suggestionsEl.innerHTML = "";
        suggestionsEl.hidden = true;
      }
      if (searchStatus) searchStatus.textContent = "";
    }

    function selectSearchResult(result) {
          var latitude = Number(result.lat);
          var longitude = Number(result.lon);
          if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) throw new Error("Invalid location");
          if (searchInput && result.display_name) searchInput.value = result.display_name;
          setLocation(latitude, longitude, "Location found. You can adjust it on the map.");
          if (searchStatus) searchStatus.textContent = "Search result selected.";
          if (suggestionsEl) {
            suggestionsEl.innerHTML = "";
            suggestionsEl.hidden = true;
          }
    }

    var suggestionTimer;
    function loadSuggestions() {
      var query = searchInput ? searchInput.value.trim() : "";
      if (!suggestionsEl || query.length < 3) {
        if (suggestionsEl) suggestionsEl.hidden = true;
        return;
      }
      window.clearTimeout(suggestionTimer);
      suggestionTimer = window.setTimeout(function () {
        var endpoint = "https://nominatim.openstreetmap.org/search?format=jsonv2&countrycodes=in&limit=5&q=" + encodeURIComponent(query);
        fetch(endpoint, { headers: { Accept: "application/json" } })
          .then(function (response) { return response.ok ? response.json() : []; })
          .then(function (results) {
            suggestionsEl.innerHTML = "";
            results.forEach(function (result) {
              var item = document.createElement("button");
              item.type = "button";
              item.className = "location-suggestion";
              item.textContent = result.display_name;
              item.addEventListener("click", function () { selectSearchResult(result); });
              suggestionsEl.appendChild(item);
            });
            suggestionsEl.hidden = results.length === 0;
          })
          .catch(function () { suggestionsEl.hidden = true; });
      }, 350);
    }

    if (searchButton) searchButton.addEventListener("click", searchLocation);
    if (searchInput) {
      searchInput.addEventListener("input", loadSuggestions);
      searchInput.addEventListener("keydown", function (event) {
        if (event.key === "Enter") {
          event.preventDefault();
          searchLocation();
        }
      });
    }

    function requestLocation() {
      clearSearchLocation();
      if (!navigator.geolocation) {
        statusEl.textContent = "Automatic location is unavailable. Select a point on the map.";
        return;
      }
      statusEl.textContent = "Getting your current location...";
      navigator.geolocation.getCurrentPosition(
        function (position) {
          setLocation(position.coords.latitude, position.coords.longitude, "Current location added.");
        },
        function () {
          statusEl.textContent = "Location permission was unavailable. Select a point on the map.";
        },
        { enableHighAccuracy: true, timeout: 10000, maximumAge: 300000 }
      );
    }

    if (useLocationButton) useLocationButton.addEventListener("click", requestLocation);
    if (map) window.setTimeout(function () { map.invalidateSize(); }, 100);

    /* Pincode -> district + state lookup (postal API, no key needed).
       Typing a 6-digit pincode fills district and state automatically;
       manual edits afterwards always win. */
    var pinTimer = null;
    function lookupPincode() {
      if (!pincodeInput) return;
      var pin = (pincodeInput.value || "").replace(/\D/g, "").slice(0, 6);
      if (pin.length !== 6) return;
      var url = "https://api.postalpincode.in/pincode/" + encodeURIComponent(pin);
      fetch(url, { headers: { Accept: "application/json" } })
        .then(function (response) {
          if (!response.ok) throw new Error("pincode lookup failed");
          return response.json();
        })
        .then(function (data) {
          var row = data && data[0];
          var offices = row && row.PostOffice;
          if (!offices || !offices.length) return;
          var first = offices[0];
          if (districtInput && !districtInput.value.trim() && first.District) {
            districtInput.value = first.District;
            districtInput.dispatchEvent(new Event("input", { bubbles: true }));
          }
          var stateEl = picker.querySelector("[data-state-for]") ||
            document.querySelector("[data-location-state]");
          if (stateEl && !stateEl.value.trim() && first.State) {
            stateEl.value = first.State;
            stateEl.dispatchEvent(new Event("input", { bubbles: true }));
          }
          if (statusEl) {
            statusEl.textContent = "Pincode matched: " + first.District +
              (first.State ? ", " + first.State : "") + ". Adjust if needed.";
          }
          /* Zoom the map into the pincode area for any Indian pincode. */
          if (map) {
            var geoUrl = "https://nominatim.openstreetmap.org/search?format=jsonv2&addressdetails=1" +
              "&countrycodes=in&limit=1&postalcode=" + encodeURIComponent(pin);
            fetch(geoUrl, { headers: { Accept: "application/json" } })
              .then(function (resp) {
                if (!resp.ok) throw new Error("pincode geocode failed");
                return resp.json();
              })
              .then(function (places) {
                if (!places || !places.length) return;
                var plat = Number(places[0].lat);
                var plon = Number(places[0].lon);
                if (!Number.isFinite(plat) || !Number.isFinite(plon)) return;
                setLocation(plat, plon, "Map zoomed to pincode " + pin + ". Adjust the pin if needed.");
              })
              .catch(function () { /* district/state already filled; map stays */ });
          }
        })
        .catch(function () { /* keep manual entry; never block */ });
    }
    if (pincodeInput) {
      pincodeInput.addEventListener("input", function () {
        window.clearTimeout(pinTimer);
        pinTimer = window.setTimeout(lookupPincode, 700);
      });
    }

    /* Auto-locate on page load where requested (report form): pin the
       citizen immediately; they can still move the pin or search. */
    if (picker.hasAttribute("data-auto-locate")) {
      var alreadyPinned = latitudeInput && latitudeInput.value;
      if (!alreadyPinned) {
        window.setTimeout(function () { requestLocation(); }, 600);
      }
    }
  });

  /* State -> district suggestions (all-India dataset). A state input with
     data-state-for="<district-datalist-id>" filters that datalist to the
     chosen state's districts; unknown states restore the fallback list.
     District stays free text — suggestions never block typing. */
  (function initStateDistricts() {
    var IN = window.INDIA_DISTRICTS || null;
    document.querySelectorAll("datalist[data-state-list]").forEach(function (dl) {
      if (!IN) return;
      dl.innerHTML = "";
      Object.keys(IN).sort().forEach(function (st) {
        var o = document.createElement("option");
        o.value = st;
        dl.appendChild(o);
      });
    });
    document.querySelectorAll("input[data-state-for]").forEach(function (stateEl) {
      var dl = document.getElementById(stateEl.getAttribute("data-state-for"));
      if (!dl || !IN) return;
      var fallback = dl.innerHTML;
      function refill() {
        var v = (stateEl.value || "").trim().toLowerCase();
        var key = Object.keys(IN).filter(function (k) {
          return k.toLowerCase() === v;
        })[0];
        dl.innerHTML = "";
        if (!key) { dl.innerHTML = fallback; return; }
        IN[key].forEach(function (d) {
          var o = document.createElement("option");
          o.value = d;
          dl.appendChild(o);
        });
      }
      stateEl.addEventListener("input", refill);
      refill();
    });
  })();
});