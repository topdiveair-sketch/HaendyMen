// app.js - simple weather dashboard using Open-Meteo (no API key)
const form = document.getElementById('searchForm');
const qInput = document.getElementById('query');
const suggestionsEl = document.getElementById('suggestions');
const statusEl = document.getElementById('status');
const currentEl = document.getElementById('current');
const currentContent = document.getElementById('currentContent');
const hourlyEl = document.getElementById('hourly');
const hourlyList = document.getElementById('hourlyList');
const dailyEl = document.getElementById('daily');
const dailyList = document.getElementById('dailyList');

const GEO_API = 'https://geocoding-api.open-meteo.com/v1/search';
const WEATHER_API = 'https://api.open-meteo.com/v1/forecast';

let debounceTimer = null;

function show(el){ el.classList.remove('hidden'); }
function hide(el){ el.classList.add('hidden'); }

function setStatus(msg, isError=false){
  statusEl.textContent = msg;
  statusEl.style.color = isError ? 'crimson' : '';
  show(statusEl);
}

// map Open-Meteo weathercode to emoji and text (simple)
const weatherCodes = {
  0: ['☀️','Clear'],
  1: ['🌤️','Mainly clear'],
  2: ['⛅','Partly cloudy'],
  3: ['☁️','Overcast'],
  45: ['🌫️','Fog'],
  48: ['🌫️','Depositing rime fog'],
  51: ['🌦️','Light drizzle'],
  53: ['🌧️','Moderate drizzle'],
  55: ['🌧️','Dense drizzle'],
  61: ['🌧️','Slight rain'],
  63: ['🌧️','Moderate rain'],
  65: ['🌧️','Heavy rain'],
  71: ['🌨️','Snow'],
  80: ['🌦️','Rain showers'],
  95: ['⛈️','Thunderstorm'],
};

function wc(code){
  return weatherCodes[code] || ['❓','Unknown'];
}

async function geocode(query){
  const url = `${GEO_API}?name=${encodeURIComponent(query)}&count=6&language=en&format=json`;
  const res = await fetch(url);
  if(!res.ok) throw new Error('Geocoding failed');
  const json = await res.json();
  return json.results || [];
}

async function fetchWeather(lat, lon){
  const url = new URL(WEATHER_API);
  url.searchParams.set('latitude', lat);
  url.searchParams.set('longitude', lon);
  url.searchParams.set('current_weather', 'true');
  url.searchParams.set('hourly', 'temperature_2m,relativehumidity_2m,precipitation');
  url.searchParams.set('daily', 'temperature_2m_max,temperature_2m_min,precipitation_sum,weathercode');
  url.searchParams.set('timezone', 'auto');
  const res = await fetch(url.toString());
  if(!res.ok) throw new Error('Weather fetch failed');
  return await res.json();
}

function renderSuggestions(results){
  suggestionsEl.innerHTML = '';
  if(!results.length){ hide(suggestionsEl); return; }
  results.forEach(r=>{
    const div = document.createElement('div');
    div.className = 'suggestion';
    div.textContent = `${r.name}${r.admin1 ? ', '+r.admin1 : ''}${r.country ? ', '+r.country : ''}`;
    div.addEventListener('click', ()=> {
      qInput.value = div.textContent;
      hide(suggestionsEl);
      lookupAndRender(r.latitude, r.longitude, div.textContent);
    });
    suggestionsEl.appendChild(div);
  });
  show(suggestionsEl);
}

function renderCurrent(weather, place){
  currentContent.innerHTML = '';
  const iconText = wc(weather.weathercode)[0];
  const desc = wc(weather.weathercode)[1];
  const el = document.createElement('div');
  el.className = 'center';
  el.innerHTML = `
    <div style="text-align:left">
      <div class="small">${place}</div>
      <div class="temp">${weather.temperature}°C</div>
      <div class="small">${desc} • wind ${weather.windspeed} km/h</div>
    </div>
    <div style="margin-left:auto;text-align:center">
      <div class="icon">${iconText}</div>
      <div class="small">${new Date(weather.time).toLocaleString()}</div>
    </div>
  `;
  currentContent.appendChild(el);
  show(currentEl);
}

function renderHourly(hourly, timezone){
  hourlyList.innerHTML = '';
  const now = new Date();
  // find current index in hourly.time
  const times = hourly.time.map(t=>new Date(t));
  let start = times.findIndex(t => t > now);
  if(start === -1) start = 0;
  const end = Math.min(start + 24, times.length);
  for(let i = start; i < end; i++){
    const h = document.createElement('div');
    h.className = 'hour';
    const t = times[i];
    const label = t.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
    const temp = hourly.temperature_2m[i];
    h.innerHTML = `<div class="small">${label}</div><div style="font-weight:800">${temp}°C</div>`;
    hourlyList.appendChild(h);
  }
  show(hourlyEl);
}

function renderDaily(daily){
  dailyList.innerHTML = '';
  const days = daily.time;
  for(let i=0;i<days.length;i++){
    const d = document.createElement('div');
    d.className = 'day';
    const date = new Date(days[i]);
    const label = date.toLocaleDateString(undefined, {weekday:'short', month:'short', day:'numeric'});
    const max = daily.temperature_2m_max[i];
    const min = daily.temperature_2m_min[i];
    const prec = daily.precipitation_sum[i];
    const code = daily.weathercode ? daily.weathercode[i] : null;
    const icon = code !== null ? wc(code)[0] : '';
    d.innerHTML = `<div class="small">${label}</div><div style="font-weight:800;margin:6px 0">${icon}</div><div>${max}° / ${min}°</div><div class="small">${prec} mm</div>`;
    dailyList.appendChild(d);
  }
  show(dailyEl);
}

async function lookupAndRender(lat, lon, placeLabel){
  try{
    setStatus('Fetching weather...');
    const data = await fetchWeather(lat, lon);
    hide(statusEl);
    if(data.current_weather){
      renderCurrent(data.current_weather, placeLabel);
    }
    if(data.hourly){
      renderHourly(data.hourly, data.timezone);
    }
    if(data.daily){
      renderDaily(data.daily);
    }
  }catch(err){
    setStatus(err.message || 'Failed to load weather', true);
  }
}

// UI handlers
form.addEventListener('submit', async (e)=>{
  e.preventDefault();
  const q = qInput.value.trim();
  if(!q) return;
  try{
    setStatus('Searching place...');
    const res = await geocode(q);
    if(res.length === 0){
      setStatus('No locations found', true);
      return;
    }
    // if exact match or single result, use it
    const first = res[0];
    hide(suggestionsEl);
    lookupAndRender(first.latitude, first.longitude, `${first.name}${first.admin1? ', '+first.admin1:''}${first.country? ', '+first.country:''}`);
  }catch(err){
    setStatus(err.message || 'Lookup failed', true);
  }
});

qInput.addEventListener('input', ()=>{
  const v = qInput.value.trim();
  clearTimeout(debounceTimer);
  if(!v){ hide(suggestionsEl); return; }
  debounceTimer = setTimeout(async ()=>{
    try{
      const res = await geocode(v);
      renderSuggestions(res);
    }catch(_){ hide(suggestionsEl); }
  }, 350);
});

// optional: start with a default location
lookupAndRender(52.5200, 13.4050, 'Berlin, Germany');
