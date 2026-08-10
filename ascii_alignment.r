# Paper - Comparing landmark-free and manual landmarking methods for macroevolutionary studies on the mammalian crania
# Original author: James M. Mulqueeney

# Alignment of Meshes using landmark-based Procrustes superimposition
# (Morpho::rotmesh.onto)
#
# Usage:
#   Rscript ascii_alignment.r --input <ascii_ply_dir> --landmarks <csv> \
#       --output <aligned_ply_dir> [--part crania|mandible] \
#       [--reference <specimen_id>] [--format binary|ascii] \
#       [--id-column <landmarks_csv_column>]
#
# --input should be a directory containing ONLY the ASCII .ply files for one
# anatomical part (e.g. 03_ascii/crania) -- the pipeline's directory layout
# already separates crania/mandible, so this script does not need to filter
# files by a part-matching filename pattern.

# Load in the correct libraries
library(Morpho)
library(geomorph)
library(abind)
library(rgl)
library(Rvcg)

#########################################################################################
# CLI ARGUMENTS
#########################################################################################

parse_args <- function(args) {
  defaults <- list(
    input = NULL,
    landmarks = NULL,
    output = NULL,
    part = "crania",
    reference = NULL,
    format = "binary",
    id_column = NULL
  )

  i <- 1
  while (i <= length(args)) {
    key <- args[[i]]
    if (!startsWith(key, "--")) {
      stop(paste("Unexpected argument (expected --flag value):", key))
    }
    name <- gsub("-", "_", sub("^--", "", key))
    if (!(name %in% names(defaults))) {
      stop(paste("Unknown argument:", key))
    }
    if (i == length(args)) {
      stop(paste("Missing value for argument:", key))
    }
    defaults[[name]] <- args[[i + 1]]
    i <- i + 2
  }

  defaults
}

usage <- paste(
  "Usage: Rscript ascii_alignment.r --input <dir> --landmarks <csv> --output <dir>",
  "[--part crania|mandible] [--reference <specimen_id>]",
  "[--format binary|ascii] [--id-column <col>]"
)

opts <- parse_args(commandArgs(trailingOnly = TRUE))

if (is.null(opts$input) || is.null(opts$landmarks) || is.null(opts$output)) {
  stop(usage)
}
if (!(opts$format %in% c("binary", "ascii"))) {
  stop(paste0("--format must be 'binary' or 'ascii', got: ", opts$format))
}

dir.create(opts$output, recursive = TRUE, showWarnings = FALSE)

#########################################################################################
# HELPERS
#########################################################################################

# Collapse whitespace/underscore/hyphen runs to a single underscore, so IDs
# from filenames and from the landmarks CSV compare equal regardless of
# separator style (mesh filenames observed in this dataset use both).
normalise_id <- function(x) {
  x <- trimws(x)
  x <- gsub("[\\s_-]+", "_", x, perl = TRUE)
  gsub("^_|_$", "", x)
}

# Derive the "Genus_species" key from a canonical mesh filename, e.g.
# "Ailuropoda_melanoleuca_crania_dec.ply" -> "Ailuropoda_melanoleuca".
species_key_from_filename <- function(filename, part) {
  stem <- sub("\\.ply$", "", filename, ignore.case = TRUE)
  stem <- sub("_dec$", "", stem, ignore.case = TRUE)
  stem <- sub(paste0("_", part, "$"), "", stem, ignore.case = TRUE)
  normalise_id(stem)
}

#########################################################################################
# LOAD MESHES
#########################################################################################

ply_files <- sort(list.files(opts$input, pattern = "\\.ply$", full.names = TRUE))

if (length(ply_files) == 0) {
  stop(paste("No .ply files found in:", opts$input))
}

original_file_names <- basename(ply_files)
cat(sprintf("Found %d mesh(es) in %s\n", length(ply_files), opts$input))

mesh_list <- list()
for (i in seq_along(ply_files)) {
  mesh_list[[i]] <- read.ply(ply_files[i], ShowSpecimen = FALSE)
}

mesh_species_keys <- vapply(
  original_file_names, species_key_from_filename, character(1), part = opts$part
)

#########################################################################################
# LOAD AND MATCH LANDMARKS
#########################################################################################

data <- read.csv(opts$landmarks, header = TRUE, stringsAsFactors = FALSE)

id_column <- if (!is.null(opts$id_column)) opts$id_column else colnames(data)[1]
if (!(id_column %in% colnames(data))) {
  stop(paste0("id column '", id_column, "' not found in ", opts$landmarks))
}

landmark_keys <- vapply(data[[id_column]], normalise_id, character(1))

# Anchored so only true x./y./z. landmark coordinate columns match -- the
# original unanchored grep("x.", ...) could match unrelated columns whose
# name happened to contain the letter x.
x_idx <- grep("^x\\.", colnames(data))
y_idx <- grep("^y\\.", colnames(data))
z_idx <- grep("^z\\.", colnames(data))

if (length(x_idx) != length(y_idx) || length(x_idx) != length(z_idx)) {
  stop(sprintf(
    "Mismatched landmark coordinate columns: %d x, %d y, %d z",
    length(x_idx), length(y_idx), length(z_idx)
  ))
}
if (length(x_idx) == 0) {
  stop("No landmark coordinate columns found (expected columns named x.1, y.1, z.1, ...)")
}

num_landmarks <- length(x_idx)
num_specimens <- nrow(data)

x_values <- as.matrix(data[, x_idx])
y_values <- as.matrix(data[, y_idx])
z_values <- as.matrix(data[, z_idx])

result_matrix <- array(0, dim = c(num_landmarks, 3, num_specimens))
for (i in 1:num_specimens) {
  result_matrix[, 1, i] <- x_values[i, ]
  result_matrix[, 2, i] <- y_values[i, ]
  result_matrix[, 3, i] <- z_values[i, ]
}

# Match meshes to landmark rows BY NAME, not by row position -- the original
# script assumed the CSV row order matched the mesh directory listing order,
# with no check, so any mismatch silently aligned every mesh to the wrong
# landmarks.
specimen_list <- vector("list", length(mesh_list))
matched_landmark_idx <- integer(0)
unmatched_meshes <- character(0)

for (i in seq_along(mesh_list)) {
  match_idx <- which(landmark_keys == mesh_species_keys[i])
  if (length(match_idx) == 0) {
    unmatched_meshes <- c(unmatched_meshes, original_file_names[i])
    next
  }
  if (length(match_idx) > 1) {
    stop(sprintf(
      "Specimen '%s' matches %d rows in %s (expected exactly 1)",
      mesh_species_keys[i], length(match_idx), opts$landmarks
    ))
  }
  specimen_list[[i]] <- result_matrix[, , match_idx[1]]
  matched_landmark_idx <- c(matched_landmark_idx, match_idx[1])
}

unmatched_landmarks <- data[[id_column]][setdiff(seq_len(num_specimens), matched_landmark_idx)]

if (length(unmatched_meshes) > 0 || length(unmatched_landmarks) > 0) {
  cat("ALIGNMENT ABORTED: meshes and landmarks could not be fully matched by name.\n")
  if (length(unmatched_meshes) > 0) {
    cat("Meshes with no matching landmark row:\n")
    cat(paste0("  - ", unmatched_meshes, collapse = "\n"), "\n")
  }
  if (length(unmatched_landmarks) > 0) {
    cat("Landmark rows with no matching mesh:\n")
    cat(paste0("  - ", unmatched_landmarks, collapse = "\n"), "\n")
  }
  quit(status = 1)
}

cat(sprintf("Matched %d mesh(es) to landmark rows by name.\n", length(mesh_list)))

#########################################################################################
# ALIGN MESHES
#########################################################################################

reference_idx <- 1
if (!is.null(opts$reference)) {
  reference_key <- normalise_id(opts$reference)
  found <- which(mesh_species_keys == reference_key)
  if (length(found) == 0) {
    stop(paste0("--reference '", opts$reference, "' does not match any mesh in --input"))
  }
  reference_idx <- found[1]
}

cat(sprintf("Using '%s' as the reference specimen.\n", original_file_names[reference_idx]))
reference_landmarks <- specimen_list[[reference_idx]]

aligned_meshes <- vector("list", length(mesh_list))
for (i in seq_along(mesh_list)) {
  aligned <- rotmesh.onto(mesh_list[[i]], specimen_list[[i]], reference_landmarks, scale = TRUE)
  aligned_meshes[[i]] <- aligned$mesh
}

#########################################################################################
# SAVE ALIGNED MESHES
#########################################################################################

for (i in seq_along(mesh_list)) {
  output_file <- file.path(opts$output, original_file_names[i])
  if (opts$format == "binary") {
    vcgPlyWrite(aligned_meshes[[i]], output_file, format = "PLY_BINARY_LE")
  } else {
    vcgPlyWrite(aligned_meshes[[i]], output_file)
  }
}

cat(sprintf("Wrote %d aligned mesh(es) to %s\n", length(mesh_list), opts$output))
quit(status = 0)
