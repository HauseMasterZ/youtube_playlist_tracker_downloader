document.addEventListener("DOMContentLoaded", () => {
    const playlistSelect = document.getElementById("playlist-select");
    const trackList = document.getElementById("track-list");
    const audioPlayer = document.getElementById("audio-player");
    const currentTitle = document.getElementById("current-title");
    const currentChannel = document.getElementById("current-channel");

    let currentPlaylistData = [];
    let currentIndex = -1;

    async function loadPlaylist(folderName) {
        trackList.innerHTML = "<li>Loading...</li>";
        
        // Define and log the exact path being requested
        const targetUrl = `./${folderName}/_Playlist_Database.json`;
        console.log(`[DEBUG] Target Fetch URL:`, targetUrl);
        console.log(`[DEBUG] Absolute URL will resolve based on:`, window.location.href);

        try {
            const response = await fetch(targetUrl);
            
            // Log the network response details
            console.log(`[DEBUG] HTTP Status:`, response.status, response.statusText);
            console.log(`[DEBUG] Resolved Final URL:`, response.url);

            if (!response.ok) {
                // If it fails (e.g., 404), attempt to read what the server actually returned
                const errorText = await response.text();
                console.log(`[DEBUG] Server Response Body:`, errorText);
                throw new Error(`HTTP Error ${response.status}: ${response.statusText}`);
            }

            currentPlaylistData = await response.json();
            console.log(`[DEBUG] Successfully parsed JSON. Track count:`, currentPlaylistData.length);
            
            renderTracks();
        } catch (error) {
            console.error(`[DEBUG] Caught Exception:`, error);
            trackList.innerHTML = `<li style="color: #ff5555;">Failed to load playlist: ${error.message}</li>`;
        }
    }
    function renderTracks() {
        trackList.innerHTML = "";
        currentPlaylistData.forEach((track, index) => {
            const li = document.createElement("li");
            li.innerHTML = `
                <span class="track-title">${index + 1}. ${escapeHtml(track.title)}</span>
                <span class="track-channel">${escapeHtml(track.channel)}</span>
            `;
            li.addEventListener("click", () => playTrack(index));
            trackList.appendChild(li);
        });
    }

    function playTrack(index) {
        if (index < 0 || index >= currentPlaylistData.length) return;
        
        currentIndex = index;
        const track = currentPlaylistData[index];

        // Update UI
        currentTitle.textContent = track.title;
        currentChannel.textContent = track.channel;

        // Highlight active track in list
        const items = trackList.querySelectorAll("li");
        items.forEach((item, idx) => {
            if (idx === index) {
                item.classList.add("active");
                item.scrollIntoView({ behavior: "smooth", block: "nearest" });
            } else {
                item.classList.remove("active");
            }
        });

        // Strictly encode file paths (handles #, &, +, etc. safely)
        const pathParts = track.file_path.split('/');
        const safePath = pathParts.map(part => encodeURIComponent(part)).join('/');
        
        // Load & Play with explicit relative pathing
        audioPlayer.src = `./${safePath}`;
        
        audioPlayer.play().catch(e => {
            console.error(`[DEBUG] Playback failed:`, e);
        });
    }

    // Add explicit error catching for the audio element
    audioPlayer.addEventListener("error", (e) => {
        console.error(`[DEBUG] Audio loading error:`, audioPlayer.error);
        currentTitle.textContent = "Error loading audio file (Check F12 Console)";
    });

    // Auto-advance to next track on end
    audioPlayer.addEventListener("ended", () => {
        if (currentIndex + 1 < currentPlaylistData.length) {
            playTrack(currentIndex + 1);
        }
    });

    // Handle playlist dropdown change
    playlistSelect.addEventListener("change", (e) => {
        loadPlaylist(e.target.value);
    });

    // Helper to sanitize text rendering
    function escapeHtml(str) {
        return str.replace(/[&<>"']/g, (m) => ({
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#039;'
        })[m]);
    }

    // Initial load
    loadPlaylist(playlistSelect.value);
});
