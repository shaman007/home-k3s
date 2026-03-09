# script/list_bookmarked_media_s3.rb
#
# Generate list of S3 URLs for media attached to bookmarked statuses.
# Output: export/bookmarked_media_s3_urls.txt
# Set BOOKMARKED_MEDIA_LOOKBACK_DAYS to reduce the time window later.

require "fileutils"
require "uri"

S3_HOST   = "https://s3.andreybondarenko.com"
S3_BUCKET = "mastodon" # path-style bucket as you described
LOOKBACK_DAYS = Integer(ENV.fetch("BOOKMARKED_MEDIA_LOOKBACK_DAYS", "90"), 10)

EXPORT_DIR  = Rails.root.join("export")
OUTPUT_PATH = EXPORT_DIR.join("bookmarked_media_s3_urls.txt")
LOOKBACK_CUTOFF = LOOKBACK_DAYS.days.ago

FileUtils.mkdir_p(EXPORT_DIR)

puts "Writing S3 URL list to: #{OUTPUT_PATH}"
puts "Filtering bookmarks created since: #{LOOKBACK_CUTOFF.iso8601}"

File.open(OUTPUT_PATH, "w") do |out|
  Bookmark
    .where("bookmarks.created_at >= ?", LOOKBACK_CUTOFF)
    .includes(status: :media_attachments)
    .find_each do |bookmark|
      status = bookmark.status
      next unless status

      status.media_attachments.each do |media|
        begin
          uploader = media.file if media.respond_to?(:file)
          next unless uploader

          key = nil

          # 1) Try file.path (often S3 key or local path)
          if uploader.respond_to?(:path) && uploader.path.present?
            path = uploader.path.to_s

            # If this is a local path with /system/ in it, strip everything up to /system/
            if path.include?("/system/")
              key = path.split("/system/", 2).last
              key = "system/#{key}"
            else
              # Otherwise assume it's already a key
              key = path.sub(%r{^/}, "")
            end
          end

          # 2) Fallback: parse from file.url if path wasn't usable
          if key.nil? && uploader.respond_to?(:url) && uploader.url.present?
            url = uploader.url.to_s

            if url.start_with?("http")
              uri = URI(url)
              # If path starts with /mastodon/, strip that as bucket prefix
              # /mastodon/system/... -> system/...
              path = uri.path.sub(%r{^/}, "")
              if path.start_with?("#{S3_BUCKET}/")
                key = path.sub(%r{^#{Regexp.escape(S3_BUCKET)}/}, "")
              else
                # If it's already like system/..., accept as key
                key = path
              end
            else
              # relative url like /system/media_attachments/...
              key = url.sub(%r{^/}, "")
            end
          end

          unless key && !key.empty?
            warn "Could not determine key for media #{media.id}, bookmark #{bookmark.id}"
            next
          end

          full_url = "#{S3_HOST}/#{S3_BUCKET}/#{key}"
          out.puts(full_url)
        rescue => e
          warn "Error for bookmark #{bookmark.id}, media #{media.id}: #{e.class} #{e.message}"
        end
      end
    end
  end
end

puts "Done."
