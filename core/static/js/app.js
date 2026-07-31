async function loadPackages(){

    const response = await fetch("/api/packages/");

    const packages = await response.json();

    let html = `
        <h2>Our Packages</h2>

        <div class="grid">
    `;

    packages.forEach(pkg=>{

        html += `
            <div class="card">

                <h3>${pkg.title}</h3>

                <h2>₹${pkg.price}</h2>

                <p>${pkg.description}</p>

                <button>
                    Buy Now
                </button>

            </div>
        `;

    });

    html += "</div>";

    document.getElementById("content").innerHTML = html;
}

window.onload = loadPackages;