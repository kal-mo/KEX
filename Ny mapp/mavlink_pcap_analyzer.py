from scapy.all import rdpcap, UDP
from pymavlink.dialects.v20 import common as mavlink2
import matplotlib.pyplot as plt
import pandas as pd
import os

# -----------------------------
# CONFIG
# -----------------------------
pcap_file = "mavlink.pcap0"

# -----------------------------
# Load PCAP file
# -----------------------------
if not os.path.exists(pcap_file):
    print(f"File not found: {pcap_file}")
    raise SystemExit

print(f"Loading: {pcap_file}")
packets = rdpcap(pcap_file)
print(f"Packets captured: {len(packets)}")

# -----------------------------
# Decode MAVLink messages
# -----------------------------
parser = mavlink2.MAVLink(None)
messages = []

for pkt in packets:
    if UDP not in pkt:
        continue

    payload = bytes(pkt[UDP].payload)
    packet_time = float(pkt.time)

    for b in payload:
        try:
            msg = parser.parse_char(bytes([b]))

            if msg:
                try:
                    msg_buf = msg.get_msgbuf()
                    msg_size = len(msg_buf) if msg_buf is not None else len(payload)
                except Exception:
                    msg_size = len(payload)

                messages.append({
                    "time": packet_time,
                    "message_type": msg.get_type(),
                    "message_id": msg.get_msgId(),
                    "packet_size": msg_size
                })

        except Exception:
            continue

# -----------------------------
# Convert to DataFrame
# -----------------------------
df_messages = pd.DataFrame(messages)

print("Loaded PCAP and parsed MAVLink messages")
print(df_messages.head())

if df_messages.empty:
    print("No MAVLink messages found. No plots generated.")
    raise SystemExit

# -----------------------------
# Normalize time
# -----------------------------
df_messages["time"] = df_messages["time"] - df_messages["time"].min()

# -----------------------------
# Save parsed messages
# -----------------------------
df_messages.to_csv("messages.csv", index=False)
print("Saved messages.csv")

# -----------------------------
# Map packet size -> dominant message type
# -----------------------------
size_to_msg = (
    df_messages.groupby("packet_size")["message_type"]
    .agg(lambda x: x.value_counts().idxmax())
)

# Add readable label: MESSAGE_TYPE (SIZEB)
df_messages["size_label"] = df_messages["packet_size"].map(
    lambda s: f"{size_to_msg[s]} ({s}B)"
)

# -----------------------------
# Plot 1: Packet size vs time
# Colored/labeled by dominant message type + size
# -----------------------------
unique_labels = df_messages["size_label"].unique()

plt.figure(figsize=(14, 6))
for label in unique_labels:
    subset = df_messages[df_messages["size_label"] == label]
    plt.scatter(
        subset["time"],
        subset["packet_size"],
        s=8,
        label=label
    )

plt.xlabel("Time (seconds)")
plt.ylabel("Packet Size (bytes)")
plt.title("MAVLink Packet Size Over Time (Message Type + Size)")
plt.grid(True)
plt.legend(
    title="Message Type (Packet Size)",
    bbox_to_anchor=(1.02, 1),
    loc="upper left",
    fontsize=8
)
plt.tight_layout()
plt.show()

# -----------------------------
# Plot 2: Message type counts
# Labeled with MESSAGE_TYPE (SIZEB)
# -----------------------------
message_summary = df_messages["size_label"].value_counts().reset_index()
message_summary.columns = ["label", "count"]

print("\nMessage type summary:")
print(message_summary)

plt.figure(figsize=(14, 6))
plt.bar(message_summary["label"], message_summary["count"])
plt.xlabel("Message Type (Packet Size)")
plt.ylabel("Count")
plt.title("MAVLink Message Type Counts")
plt.xticks(rotation=90)
plt.grid(True, axis="y")
plt.tight_layout()
plt.show()

# -----------------------------
# Plot 3: Message frequency over time
# Show all message types that appear in the data
# -----------------------------
bin_size_freq = 1.0  # 1 second bins
df_messages["time_bin_freq"] = (
    (df_messages["time"] / bin_size_freq).astype(int) * bin_size_freq
)

freq = (
    df_messages.groupby(["time_bin_freq", "message_type"])
    .size()
    .unstack(fill_value=0)
)

# Ensure all message types are included
all_message_types = sorted(df_messages["message_type"].unique())
freq = freq.reindex(columns=all_message_types, fill_value=0)

plt.figure(figsize=(16, 8))
for col in freq.columns:
    plt.plot(freq.index, freq[col], linewidth=1.2, label=col)

plt.xlabel("Time (seconds)")
plt.ylabel("Messages per second")
plt.title("MAVLink Message Frequency Over Time")
plt.grid(True)
plt.legend(
    title="Message Type",
    bbox_to_anchor=(1.02, 1),
    loc="upper left",
    fontsize=8
)
plt.tight_layout()
plt.show()

# -----------------------------
# Plot 4: Number of active message types
# -----------------------------
bin_size_active = 0.01  # 10 ms bins
df_messages["time_bin_active"] = (
    (df_messages["time"] / bin_size_active).astype(int) * bin_size_active
)

active_types = df_messages.groupby("time_bin_active")["message_type"].nunique()

plt.figure(figsize=(16, 6))
plt.plot(active_types.index, active_types.values, linewidth=1.5)
plt.xlabel("Time (seconds)")
plt.ylabel("Number of Different Message Types")
plt.title("Simultaneous MAVLink Message Types")
plt.grid(True)
plt.tight_layout()
plt.show()

# -----------------------------
# Plot 5: Boolean heatmap
# Active = 1, Inactive = 0
# -----------------------------
heatmap_counts = (
    df_messages.groupby(["time_bin_active", "message_type"])
    .size()
    .unstack(fill_value=0)
)

heatmap_bool = (heatmap_counts > 0).astype(int)

plt.figure(figsize=(16, 8))
plt.imshow(
    heatmap_bool.T,
    aspect="auto",
    origin="lower",
    cmap="binary",
    interpolation="nearest"
)

plt.colorbar(label="Active (1) / Inactive (0)")
plt.yticks(range(len(heatmap_bool.columns)), heatmap_bool.columns)
plt.xlabel("Time bin (10 ms)")
plt.ylabel("Message Type")
plt.title("MAVLink Message Activity Heatmap (Boolean)")
plt.tight_layout()
plt.show()
