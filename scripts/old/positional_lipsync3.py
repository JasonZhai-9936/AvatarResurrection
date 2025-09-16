import os
import whisper
import re
from moviepy import VideoFileClip, concatenate_videoclips
import syllables
from pathlib import Path

# Ensure ffmpeg is available
FFMPEG_BIN_PATH = r"C:\ffmpeg\bin"
os.environ["PATH"] = FFMPEG_BIN_PATH + os.pathsep + os.environ.get("PATH", "")

class LipSyncGenerator:
    def __init__(self, video_clips_folder, backup_clips=None):
        """
        Initialize the lip sync generator
        
        Args:
            video_clips_folder (str): Path to folder containing video clips
            backup_clips (dict): Dictionary mapping syllable counts to backup clip names
        """
        self.video_clips_folder = video_clips_folder
        self.model = whisper.load_model("tiny")
        
        # Default backup clips for different syllable counts
        self.backup_clips = backup_clips or {
            1: "main_a.mp4",     # 1 syllable
            2: "main_about.mp4",  # 2 syllables  
            3: "main_activity.mp4", # 3 syllables
            4: "main_community.mp4", # 4 syllables
            5: "main_opportunity.mp4"  # 5 syllables
        }
        
        # Load available video clips
        self.available_clips = self._load_available_clips()
        
    def _load_available_clips(self):
        """Load all available video clips and map them to words"""
        clips = {}
        clip_folder = Path(self.video_clips_folder)
        
        for clip_file in clip_folder.glob("*.mp4"):
            # Extract word from filename (remove main_ prefix and .mp4 suffix)
            filename = clip_file.stem
            if filename.startswith("main_"):
                word = filename[5:]  # Remove "main_" prefix
                
                # Handle numbered duplicates (e.g., main_some_002_some_002.mp4)
                word = re.sub(r'_\d+.*', '', word)
                
                clips[word.lower()] = str(clip_file)
                
        return clips
    
    def _clean_word(self, word):
        """Clean word by removing punctuation and converting to lowercase"""
        return re.sub(r'[^\w]', '', word.lower())
    
    def _get_syllable_count(self, word):
        """Get syllable count for a word"""
        try:
            return syllables.estimate(word)
        except:
            # Fallback method if syllables library fails
            word = word.lower()
            vowels = "aeiouy"
            count = 0
            prev_was_vowel = False
            
            for char in word:
                is_vowel = char in vowels
                if is_vowel and not prev_was_vowel:
                    count += 1
                prev_was_vowel = is_vowel
                
            return max(1, count)
    
    def _find_best_clip(self, word):
        """Find the best video clip for a given word"""
        clean_word = self._clean_word(word)
        
        # First try exact match
        if clean_word in self.available_clips:
            return self.available_clips[clean_word]
        
        # If no exact match, use syllable-based backup
        syllable_count = self._get_syllable_count(clean_word)
        
        # Cap at 5 syllables for backup clips
        syllable_count = min(syllable_count, 5)
        
        backup_clip = self.backup_clips.get(syllable_count, self.backup_clips[1])
        backup_path = os.path.join(self.video_clips_folder, backup_clip)
        
        if os.path.exists(backup_path):
            return backup_path
        
        # If backup doesn't exist, use first available clip
        if self.available_clips:
            return list(self.available_clips.values())[0]
        
        raise FileNotFoundError("No video clips found in the specified folder")
    
    def _adjust_clip_duration(self, clip, target_duration):
        """Adjust clip duration to match target duration"""
        current_duration = clip.duration
        
        if abs(current_duration - target_duration) < 0.01:  # Close enough
            return clip
        
        if current_duration > target_duration:
            # Speed up the clip by trimming and adjusting
            speed_factor = current_duration / target_duration
            return clip.speedx(speed_factor)
        else:
            # Slow down or extend the clip
            if target_duration <= current_duration * 3:
                # Slow down if target is within 3x current duration
                speed_factor = current_duration / target_duration
                return clip.speedx(speed_factor)
            else:
                # Extend by looping the last frame
                extension_duration = target_duration - current_duration
                last_frame_time = max(0, current_duration - 0.1)
                last_frame = clip.to_ImageClip(t=last_frame_time, duration=extension_duration)
                return concatenate_videoclips([clip, last_frame])
    
    def transcribe_audio(self, audio_path):
        """Transcribe audio and return word-level timestamps"""
        print(f"Transcribing audio: {audio_path}")
        result = self.model.transcribe(audio_path, word_timestamps=True)
        
        words_with_timing = []
        for segment in result["segments"]:
            for w in segment["words"]:
                words_with_timing.append({
                    'word': w['word'].strip(),
                    'start': w['start'],
                    'end': w['end'],
                    'duration': w['end'] - w['start']
                })
        
        return words_with_timing
    
    def generate_lip_sync_video(self, audio_path, output_path):
        """Generate lip-synced video from audio"""
        print("Starting lip sync video generation...")
        
        # Get word timings from audio
        word_timings = self.transcribe_audio(audio_path)
        
        if not word_timings:
            raise ValueError("No words detected in audio")
        
        print(f"Found {len(word_timings)} words to process")
        
        # Generate video clips for each word
        video_clips = []
        
        for i, word_info in enumerate(word_timings):
            word = word_info['word']
            duration = word_info['duration']
            
            print(f"Processing word {i+1}/{len(word_timings)}: '{word}' (duration: {duration:.2f}s)")
            
            # Find appropriate video clip
            clip_path = self._find_best_clip(word)
            print(f"  Using clip: {os.path.basename(clip_path)}")
            
            # Load and adjust video clip
            try:
                video_clip = VideoFileClip(clip_path)
                
                # Handle very short durations (minimum 0.1 seconds)
                duration = max(duration, 0.1)
                
                adjusted_clip = self._adjust_clip_duration(video_clip, duration)
                video_clips.append(adjusted_clip)
                
                # Close the original clip to free memory
                video_clip.close()
                
            except Exception as e:
                print(f"  Warning: Error processing clip for '{word}': {e}")
                # Use a default short clip if there's an error
                if video_clips:
                    # Use a simple subclip from the last successful clip
                    try:
                        last_clip = video_clips[-1]
                        simple_clip = last_clip.subclip(0, min(duration, last_clip.duration))
                        if simple_clip.duration < duration:
                            # Extend with last frame if needed
                            extension = simple_clip.to_ImageClip(duration=duration - simple_clip.duration)
                            simple_clip = concatenate_videoclips([simple_clip, extension])
                        video_clips.append(simple_clip)
                    except:
                        print(f"  Skipping word '{word}' due to errors")
                        continue
        
        if not video_clips:
            raise ValueError("No video clips could be generated")
        
        print("Concatenating video clips...")
        
        # Concatenate all video clips
        final_video = concatenate_videoclips(video_clips, method="compose")
        
        # Load original audio and set it to the video
        print("Adding audio track...")
        from moviepy.editor import AudioFileClip
        try:
            audio_clip = AudioFileClip(audio_path)
            final_video = final_video.set_audio(audio_clip)
        except Exception as e:
            print(f"Warning: Could not load audio file: {e}")
        
        # Export final video
        print(f"Exporting final video to: {output_path}")
        final_video.write_videofile(
            output_path, 
            codec='libx264',
            audio_codec='aac',
            temp_audiofile='temp-audio.m4a',
            remove_temp=True,
            verbose=False,
            logger=None
        )
        
        # Clean up
        final_video.close()
        for clip in video_clips:
            clip.close()
        
        print("Lip sync video generation completed!")
        return output_path

def run_lipsync():
    """Main function to run lip sync generation"""
    
    # ============ UPDATE THESE PATHS ============
    VIDEO_CLIPS_FOLDER = r"C:\Users\Jason\Desktop\Important\Projects\AvatarResurrection\avatars\Darwin\movinghead\word_clips\main"
    AUDIO_PATH = r"C:\Users\Jason\Desktop\Important\Projects\AvatarResurrection\tempstream\d2.wav"
    OUTPUT_PATH = r"C:\Users\Jason\Desktop\Important\Projects\AvatarResurrection\lipsync_result.mp4"
    # ============================================
    
    print("=== Lip Sync Video Generator ===")
    print(f"Video clips folder: {VIDEO_CLIPS_FOLDER}")
    print(f"Audio file: {AUDIO_PATH}")
    print(f"Output will be saved to: {OUTPUT_PATH}")
    print()
    
    # Create the generator
    lip_sync = LipSyncGenerator(VIDEO_CLIPS_FOLDER)
    
    print(f"Found {len(lip_sync.available_clips)} video clips:")
    for word in sorted(list(lip_sync.available_clips.keys())[:10]):  # Show first 10
        print(f"  - {word}")
    if len(lip_sync.available_clips) > 10:
        print(f"  ... and {len(lip_sync.available_clips) - 10} more")
    print()
    
    # Generate the lip-synced video
    try:
        result = lip_sync.generate_lip_sync_video(AUDIO_PATH, OUTPUT_PATH)
        print(f"\n✅ SUCCESS! Video generated: {result}")
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # Install required packages first:
    # pip install openai-whisper moviepy syllables
    
    run_lipsync()