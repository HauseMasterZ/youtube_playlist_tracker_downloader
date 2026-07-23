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
        try {
            const response = await fetch(`${folderName}/_Playlist_Database.json`);
            if (!response.ok) throw new Error("JSON not found");
            currentPlaylistData = await response.json();
            renderTracks();
        } catch (error) {
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

        // UpdateUI
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

        // Load & Play
        audioPlayer.src = encodeURI(track.file_path);
        audioPlayer.play();
    }

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
