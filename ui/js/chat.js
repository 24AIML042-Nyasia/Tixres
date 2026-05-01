/**
 * chat.js – Chatbot frontend logic.
 */
import { CHAT_ENDPOINT } from "./config.js";

document.addEventListener("DOMContentLoaded", () => {
    const chatWidget = document.getElementById("chat-widget");
    const chatHeader = document.getElementById("chat-header");
    const chatBody = document.getElementById("chat-body");
    const chatToggle = document.getElementById("chat-toggle");
    const chatInput = document.getElementById("chat-input");
    const chatSend = document.getElementById("chat-send");
    const chatMessages = document.getElementById("chat-messages");

    let isOpen = false;

    // Toggle chat visibility
    chatHeader.addEventListener("click", () => {
        isOpen = !isOpen;
        chatBody.style.display = isOpen ? "flex" : "none";
        chatToggle.textContent = isOpen ? "×" : "—";
        if (isOpen) {
            chatInput.focus();
        }
    });

    const addMessage = (text, type) => {
        const msg = document.createElement("div");
        msg.className = `msg ${type}`;
        msg.textContent = text;
        chatMessages.appendChild(msg);
        chatMessages.scrollTop = chatMessages.scrollHeight;
    };

    const sendMessage = async () => {
        const text = chatInput.value.trim();
        if (!text) return;

        addMessage(text, "user");
        chatInput.value = "";

        // Add loading indicator
        const loadingMsg = document.createElement("div");
        loadingMsg.className = "msg bot loading";
        loadingMsg.textContent = "...";
        chatMessages.appendChild(loadingMsg);
        chatMessages.scrollTop = chatMessages.scrollHeight;

        try {
            const response = await fetch(CHAT_ENDPOINT, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ message: text })
            });

            const data = await response.json();
            chatMessages.removeChild(loadingMsg);

            if (data.response) {
                addMessage(data.response, "bot");
            } else {
                addMessage("Sorry, I encountered an error.", "bot");
            }
        } catch (error) {
            chatMessages.removeChild(loadingMsg);
            addMessage("Service unavailable. Is the chatbot microservice running?", "bot");
            console.error("Chat error:", error);
        }
    };

    chatSend.addEventListener("click", sendMessage);
    chatInput.addEventListener("keypress", (e) => {
        if (e.key === "Enter") sendMessage();
    });
});
