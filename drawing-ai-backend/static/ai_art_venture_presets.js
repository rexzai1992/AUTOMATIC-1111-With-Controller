(() => {
  const themes = [
    {
      id: "underwater-world",
      name: "Underwater World",
      prompt:
        "a colorful underwater world with coral reefs, bubbles, tropical fish, soft blue light rays, magical ocean plants, dreamy water atmosphere"
    },
    {
      id: "magical-theme-park",
      name: "Magical Theme Park",
      prompt:
        "a magical theme park environment with colorful lights, fantasy booths, glowing decorations, balloons, soft bokeh lights, playful props, cinematic depth of field"
    },
    {
      id: "candy-wonderland",
      name: "Candy Wonderland",
      prompt:
        "a bright candy wonderland with giant lollipops, pastel candy trees, chocolate paths, colorful sweets, soft clouds, cheerful lighting"
    },
    {
      id: "fantasy-forest",
      name: "Fantasy Forest",
      prompt:
        "an enchanted fantasy forest with glowing mushrooms, fireflies, magical plants, soft sunlight rays, dreamy atmosphere, colorful flowers"
    },
    {
      id: "space-adventure",
      name: "Space Adventure",
      prompt:
        "a fun space adventure background with planets, stars, glowing nebula, floating asteroids, futuristic lights, colorful galaxy sky"
    },
    {
      id: "dinosaur-jungle",
      name: "Dinosaur Jungle",
      prompt:
        "a playful dinosaur jungle with giant leaves, volcano in the distance, friendly dinosaur silhouettes, tropical plants, adventure lighting"
    },
    {
      id: "toy-workshop",
      name: "Toy Workshop",
      prompt:
        "a cozy toy workshop with wooden tables, colorful craft tools, shelves of toys, warm lights, creative handmade decorations"
    },
    {
      id: "art-studio",
      name: "Art Studio",
      prompt:
        "a colorful art studio with paint splashes, canvases, brushes, craft materials, cheerful wall decorations, warm creative lighting"
    },
    {
      id: "dreamy-cloud-kingdom",
      name: "Dreamy Cloud Kingdom",
      prompt:
        "a dreamy cloud kingdom with fluffy clouds, pastel sky, floating stars, soft rainbow light, magical castle shapes in the distance"
    },
    {
      id: "superhero-city",
      name: "Superhero City",
      prompt:
        "a bright superhero city rooftop with skyline, comic-style lights, action atmosphere, colorful buildings, dramatic but child-friendly background"
    },
    {
      id: "jungle-adventure",
      name: "Jungle Adventure",
      prompt:
        "a lush jungle adventure scene with vines, big tropical leaves, hidden temple stones, golden sunlight, explorer-style atmosphere"
    },
    {
      id: "winter-snow-village",
      name: "Winter Snow Village",
      prompt:
        "a cozy winter snow village with snowy rooftops, warm glowing windows, soft snowfall, pine trees, festive lights"
    },
    {
      id: "rainbow-playground",
      name: "Rainbow Playground",
      prompt:
        "a cheerful rainbow playground with slides, swings, soft grass, colorful play equipment, balloons, bright sunny sky"
    },
    {
      id: "castle-fantasy",
      name: "Castle Fantasy",
      prompt:
        "a fairytale castle courtyard with stone paths, colorful banners, flowers, glowing windows, magical fantasy atmosphere"
    },
    {
      id: "futuristic-neon-city",
      name: "Futuristic Neon City",
      prompt:
        "a futuristic neon city with glowing signs, cyber-style lights, reflective floor, colorful holograms, cinematic night atmosphere"
    },
    {
      id: "pirate-island",
      name: "Pirate Island",
      prompt:
        "a playful pirate island with palm trees, wooden treasure chest, beach sand, small ship in the background, sunset adventure lighting"
    },
    {
      id: "farm-village",
      name: "Farm Village",
      prompt:
        "a cute farm village with green fields, wooden fence, barn, animals in the distance, warm sunlight, peaceful countryside mood"
    },
    {
      id: "circus-carnival",
      name: "Circus Carnival",
      prompt:
        "a colorful circus carnival with striped tents, flags, balloons, glowing bulbs, playful booths, festive atmosphere"
    },
    {
      id: "robot-laboratory",
      name: "Robot Laboratory",
      prompt:
        "a friendly robot laboratory with glowing screens, cute robots, science tools, neon blue lights, clean futuristic background"
    },
    {
      id: "storybook-town",
      name: "Storybook Town",
      prompt:
        "a charming storybook town with cute houses, cobblestone street, flower pots, warm lights, soft whimsical atmosphere"
    }
  ];

  const styles = [
    {
      id: "pixar_3d",
      name: "Pixar 3D",
      backendStyleId: "pixar_3d",
      styleRiskLevel: "experimental",
      prompt:
        "3D animated movie style, expressive stylized face, soft cinematic lighting, polished colorful render, family friendly, high quality 3D character design"
    },
    {
      id: "disney_3d",
      name: "Disney 3D",
      backendStyleId: "disney_3d",
      styleRiskLevel: "experimental",
      prompt:
        "magical 3D animated film style, soft expressive character design, warm cinematic lighting, polished family movie render, colorful charming atmosphere"
    },
    {
      id: "anime_movie",
      name: "Anime Movie",
      backendStyleId: "anime_movie",
      styleRiskLevel: "balanced",
      prompt:
        "high quality anime movie style, clean linework, cinematic anime lighting, expressive stylized eyes, rich color grading, detailed atmospheric background"
    },
    {
      id: "watercolor",
      name: "Watercolor",
      backendStyleId: "watercolor",
      styleRiskLevel: "safe",
      prompt:
        "traditional watercolor painting, soft pigment bloom, paper grain texture, hand-painted washes, gentle colors, artistic brush softness"
    },
    {
      id: "oil_painting",
      name: "Oil Painting",
      backendStyleId: "oil_painting",
      styleRiskLevel: "balanced",
      prompt:
        "classic oil painting style, rich brush strokes, painterly texture, warm museum lighting, detailed artistic portrait feel"
    },
    {
      id: "renaissance",
      name: "Renaissance",
      backendStyleId: "renaissance",
      styleRiskLevel: "balanced",
      prompt:
        "renaissance inspired painting, classical composition, warm old-master lighting, fine painterly details, elegant artistic atmosphere"
    },
    {
      id: "da_vinci",
      name: "Da Vinci",
      backendStyleId: "da_vinci",
      styleRiskLevel: "balanced",
      prompt:
        "Leonardo da Vinci inspired sketch and painting hybrid, sepia tones, classical study drawing texture, old manuscript atmosphere, refined artistic detail"
    },
    {
      id: "comic_book",
      name: "Comic Book",
      backendStyleId: "comic_book",
      styleRiskLevel: "safe",
      prompt:
        "bold comic book ink lines, vivid comic colors, halftone shading, dynamic contrast, graphic novel finish, clean expressive outlines"
    },
    {
      id: "manga",
      name: "Manga",
      backendStyleId: "manga",
      styleRiskLevel: "balanced",
      prompt:
        "manga illustration style, crisp black linework, screentone shading, expressive stylized face, dramatic panel-like lighting, clean composition"
    },
    {
      id: "doodle",
      name: "Doodle",
      backendStyleId: "doodle",
      styleRiskLevel: "safe",
      prompt:
        "playful doodle illustration style, marker texture, hand-drawn whimsical line energy, colorful simple shapes, fun sketchbook atmosphere"
    },
    {
      id: "lego_3d",
      name: "LEGO 3D",
      backendStyleId: "lego_3d",
      styleRiskLevel: "experimental",
      prompt:
        "LEGO brick-built 3D style, plastic toy material, colorful brick textures, miniature toy world, playful blocky render"
    },
    {
      id: "clay_toy",
      name: "Clay Toy",
      backendStyleId: "clay_toy",
      styleRiskLevel: "safe",
      prompt:
        "stop-motion clay toy style, handcrafted clay texture, soft cinematic lighting, charming handmade model look, family friendly"
    },
    {
      id: "plush_toy",
      name: "Plush Toy",
      backendStyleId: "plush_toy",
      styleRiskLevel: "balanced",
      prompt:
        "plush toy fabric style, stitched details, soft fuzzy textures, cozy lighting, cute toy-like character design"
    },
    {
      id: "fantasy_epic",
      name: "Fantasy Epic",
      backendStyleId: "fantasy_epic",
      styleRiskLevel: "balanced",
      prompt:
        "epic fantasy concept art style, magical lighting, glowing atmosphere, ornate details, heroic fantasy environment, cinematic depth"
    },
    {
      id: "cyberpunk",
      name: "Cyberpunk",
      backendStyleId: "cyberpunk",
      styleRiskLevel: "balanced",
      prompt:
        "cyberpunk neon city style, futuristic lighting, glowing signs, vibrant neon reflections, sci-fi atmosphere, cinematic night scene"
    },
    {
      id: "steampunk",
      name: "Steampunk",
      backendStyleId: "steampunk",
      styleRiskLevel: "balanced",
      prompt:
        "steampunk fantasy style, brass gears, vintage machinery, Victorian adventure atmosphere, warm mechanical details, cinematic lighting"
    },
    {
      id: "minecraft",
      name: "Minecraft",
      backendStyleId: "minecraft",
      styleRiskLevel: "experimental",
      prompt:
        "Minecraft voxel world style, block-based geometry, pixel textures, game-like lighting, stylized square forms, colorful block environment"
    },
    {
      id: "low_poly",
      name: "Low Poly",
      backendStyleId: "low_poly",
      styleRiskLevel: "experimental",
      prompt:
        "low poly 3D style, faceted geometric shapes, clean polygonal character design, stylized lighting, simple colorful environment"
    },
    {
      id: "storybook",
      name: "Storybook",
      backendStyleId: "storybook",
      styleRiskLevel: "safe",
      prompt:
        "children's storybook illustration style, warm narrative lighting, painterly textures, charming colorful scenery, family friendly magical atmosphere"
    },
    {
      id: "paper_cut",
      name: "Paper Cut",
      backendStyleId: "paper_cut",
      styleRiskLevel: "safe",
      prompt:
        "layered paper-cut collage style, stacked cardstock textures, soft shadow depth, handcrafted paper art scene, clean cutout shapes"
    }
  ];

  window.AI_ART_VENTURE_THEME_PRESETS = themes;
  window.AI_ART_VENTURE_STYLE_PRESETS = styles;
  window.AI_ART_VENTURE_DEFAULTS = {
    enabled: false,
    randomStyleEnabled: true,
    randomThemeEnabled: false,
    selectedStyleId: "pixar_3d",
    selectedThemeId: "underwater-world",
    customTheme: ""
  };
  window.AI_ART_VENTURE_NEGATIVE_APPEND =
    "white background, plain background, empty background, transparent background, studio background, blank wall, " +
    "boring background, missing background, gender change, different person, different face, changed hairstyle, " +
    "changed shirt, different outfit, suit, dress, costume, uniform, changed object, missing object, replaced creation, " +
    "cropped object, hidden hands, bad hands, extra fingers, deformed fingers, blurry face, distorted face, low quality, " +
    "scary, creepy, horror, dark violent scene";
})();
